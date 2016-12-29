import cherrypy
import logging
import json
import subprocess
from threading import Thread


class Mountable(object):
    """
    Macro for encapsulating a component's config and methods into one object.
    :param conf: cherrypy config dict for use when mounting this component
    """
    def __init__(self, conf=None):
        self.conf = conf if conf else {'/': {}}

    def mount(self, path):
        """
        Mount this component into the cherrypy tree
        :param path: where to mount it e.g. /v1
        :return: self
        """
        cherrypy.tree.mount(self, path, self.conf)
        return self


class ZApi(object):
    def __init__(self, master):
        """
        Main component of the API service. Inits and assembles the various classes. Provides .run() and .stop() to
        control it.
        :param master: parent BastionController reference.
        """
        self.master = master
        self.app_v1 = ZApiV1(self).mount('/api/v1')
        # self.app_root = BSApiRoot(self).mount('/api')
        # self.ui = Mountable(conf={'/': {
        #                          'tools.staticdir.on': True,
        #                          'tools.staticdir.dir': os.getcwd() + '/ui/build',  # TODO don't hardcode
        #                          'tools.staticdir.index': 'index.html'}}).mount('/ui')

        cherrypy.config.update({
            'sessionFilter.on': True,
            'tools.sessions.on': True,
            'tools.sessions.locking': 'explicit',
            'tools.sessions.timeout': 525600,
            'request.show_tracebacks': True,
            'server.socket_port': 3000,  # TODO configurable port
            'server.thread_pool': 25,
            'server.socket_host': '0.0.0.0',
            'server.show_tracebacks': True,
            'server.socket_timeout': 5,
            'log.screen': False,
            'engine.autoreload.on': False
        })

    def run(self):
        cherrypy.engine.start()
        cherrypy.engine.block()
        logging.info("API has shut down")

    def stop(self):
        cherrypy.engine.exit()
        logging.info("API shutting down...")


class ZApiV1(Mountable):
    """
    Provides the /v1/ api.
    """
    def __init__(self, root):
        super().__init__(conf={
            "/machine": {'request.dispatch': cherrypy.dispatch.MethodDispatcher()},
            # "/task": {'request.dispatch': cherrypy.dispatch.MethodDispatcher()},  # @TODO this conf belongs in the child
            # "/logs": {
            #     'tools.staticdir.on': True,
            #     'tools.staticdir.dir': root.master.log_path,
            #     'tools.staticdir.content_types': {'log': 'text/plain'}
            # }
        })
        self.root = root
        self.machine = ZApiMachines(self.root)
        # self.task = BSApiTask(self.root)
        # self.control = BSApiControl(self.root)
        # self.socket = ApiWebsockets(self.root)

    @cherrypy.expose
    def index(self):
        yield "It works!"

    @cherrypy.expose
    def create_disk(self, datastore, name, size, fmt):
        """
        WORKAROUND for creating qemu disks
        TODO replace me
        """
        assert fmt in ["qcow2", "raw"], "Disk format is invalid"
        assert name.endswith(".bin"), "Disk must be named <something>.bin"
        self.root.master.create_disk(datastore, name, fmt, size)

        return name


@cherrypy.popargs("machine_id")
class ZApiMachineStop(object):
    """
    Endpoint to stop running machines
    """
    exposed = True

    def __init__(self, root):
        self.root = root

    @cherrypy.tools.json_out()
    def GET(self, machine_id):
        """
        If the machine exists, stop it gracefully. This happens asynchronously.
        """
        assert machine_id in self.root.master.machines
        Thread(target=lambda: self.root.master.forceful_stop(machine_id)).start()
        return machine_id


@cherrypy.popargs("machine_id")
class ZApiMachineStart(object):
    """
    Endpoint to start stopped machines
    """
    exposed = True

    def __init__(self, root):
        self.root = root

    @cherrypy.tools.json_out()
    def GET(self, machine_id=None):
        """
        Start the machine
        """
        self.root.master.machines[machine_id].start()
        return machine_id


@cherrypy.popargs("machine_id")
class ZApiMachineRestart(object):
    """
    Endpoint to restart machines
    """
    exposed = True

    def __init__(self, root):
        self.root = root

    @cherrypy.tools.json_out()
    def GET(self, machine_id=None):
        """
        Start the machine
        TODO can we not repeat this from Stop/Start?
        """
        assert machine_id in self.root.master.machines
        self.root.master.forceful_stop(machine_id)
        self.root.master.machines[machine_id].start()
        return machine_id


@cherrypy.popargs("machine_id")
class ZApiMachines():
    """
    Endpoint for managing machines
    """

    exposed = True

    def __init__(self, root):
        """
        Endpoint to modify machines. PUT and DELETE require the machine not be running, which can be managed with the
        stop and start methods below
        """
        self.root = root
        self.stop = ZApiMachineStop(self.root)
        self.start = ZApiMachineStart(self.root)
        self.restart = ZApiMachineRestart(self.root)

    @cherrypy.tools.json_out()
    def GET(self, machine_id=None, action=None, summary=False):
        """
        Get a list of all machines or specific one if passed
        :param task_id: task to retrieve
        """
        summary = summary in [True, 'True', 'true', 'yes', '1', 1]

        machines = {}
        for _machine_id, machine_spec in self.root.master.machines.items():
            machine = {"machine_id": _machine_id,
                       "_status": machine_spec.machine.get_status()}
            if not summary:
                machine.update({"machine_type": machine_spec.machine_type,
                                "spec": machine_spec.serialize()})

            machines[_machine_id] = machine
        if machine_id is not None:
            try:
                return [machines[machine_id]]
            except KeyError:
                raise cherrypy.HTTPError(status=404)
        else:
            return list(machines.values())

    @cherrypy.tools.json_out()
    def PUT(self, machine_id, machine_type, machine_spec):
        """
        Create a new machine or update an existing machine
        :param machine_id: id of machine to create or modify
        :param machine_type: set machine type (currently, only "q")
        'param machine_spec: json dictionary describing the machine. see the 'spec' key of example/banutoo.json
        """

        assert machine_id not in self.root.master.machines or \
            self.root.master.machines[machine_id].machine.get_status() == "stopped", \
            "Machine must be stopped to modify"

        machine_spec = json.loads(machine_spec)
        self.root.master.add_machine(machine_id, machine_type, machine_spec, write=True)
        return machine_id

    def DELETE(self, machine_id):
        """
        Delete a machine. Raises 404 if no machine exists. Raises error if machine is not stopped
        :param machine_id: ID of machine to remove
        """
        try:
            assert self.root.master.machines[machine_id].machine.get_status() == "stopped", \
                "Machine must be stopped to delete"
        except KeyError:
            raise cherrypy.HTTPError(status=404)

        self.root.master.remove_machine(machine_id)
        return machine_id

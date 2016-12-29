import cherrypy
import logging
import json
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
        #                          'tools.staticdir.dir': os.getcwd() + '/ui/build',
        #                          'tools.staticdir.index': 'index.html'}}).mount('/ui')

        cherrypy.config.update({
            'sessionFilter.on': True,
            'tools.sessions.on': True,
            'tools.sessions.locking': 'explicit',
            'tools.sessions.timeout': 525600,
            'request.show_tracebacks': True,
            'server.socket_port': self.master.config.get("apiport", 3000),
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
            "/disk": {'request.dispatch': cherrypy.dispatch.MethodDispatcher()},
            # "/task": {'request.dispatch': cherrypy.dispatch.MethodDispatcher()},
            # "/logs": {
            #     'tools.staticdir.on': True,
            #     'tools.staticdir.dir': root.master.log_path,
            #     'tools.staticdir.content_types': {'log': 'text/plain'}
            # }
        })
        self.root = root
        self.machine = ZApiMachines(self.root)
        self.disk = ZApiDisks(self.root)
        # self.task = BSApiTask(self.root)
        # self.control = BSApiControl(self.root)
        # self.socket = ApiWebsockets(self.root)

    @cherrypy.expose
    def index(self):
        yield "It works!"


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
        """
        assert machine_id in self.root.master.machines
        self.root.master.forceful_stop(machine_id)
        self.root.master.machines[machine_id].start()
        return machine_id


@cherrypy.popargs("prop")
class ZApiMachineProperty(object):
    """
    Endpoint to modify machine properties
    """
    exposed = True

    def __init__(self, root):
        self.root = root

    @cherrypy.tools.json_out()
    def GET(self, machine_id, prop):
        """
        Fetch a property from a machine
        """
        try:
            machine = self.root.master.machines[machine_id]
            return machine.properties[prop]
        except KeyError:
            raise cherrypy.HTTPError(status=404)

    @cherrypy.tools.json_out()
    def PUT(self, machine_id, prop, value):
        """
        Set a property on a machine.
        """
        value = json.loads(value)
        try:
            machine = self.root.master.machines[machine_id]
            assert machine.machine.get_status() == "stopped", "Machine must be stopped to modify"

        except KeyError:
            raise cherrypy.HTTPError(status=404)

        machine.properties[prop] = value
        machine.save()
        return [machine_id, prop, value]

    @cherrypy.tools.json_out()
    def DELETE(self, machine_id, prop):
        """
        Remove a property on a machine.
        """
        try:
            machine = self.root.master.machines[machine_id]
            assert machine.machine.get_status() == "stopped", "Machine must be stopped to modify"
        except KeyError:
            raise cherrypy.HTTPError(status=404)

        del machine.properties[prop]
        machine.save()
        return [machine_id, prop]


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
        self.property = ZApiMachineProperty(self.root)

    @cherrypy.tools.json_out()
    def GET(self, machine_id=None, summary=False):
        """
        Get a list of all machines or specific one if passed
        :param machine_id: machine to retrieve
        """
        summary = summary in [True, 'True', 'true', 'yes', '1', 1]

        machines = {}
        for _machine_id, machine_spec in self.root.master.machines.items():
            machine = {"machine_id": _machine_id,
                       "_status": machine_spec.machine.get_status()}
            if not summary:
                machine.update({"properties": machine_spec.serialize()})

            machines[_machine_id] = machine
        if machine_id is not None:
            try:
                return [machines[machine_id]]
            except KeyError:
                raise cherrypy.HTTPError(status=404)
        else:
            return list(machines.values())

    @cherrypy.tools.json_out()
    def PUT(self, machine_id, machine_spec):
        """
        Create a new machine or update an existing machine
        :param machine_id: id of machine to create or modify
        'param machine_spec: json dictionary describing the machine. see the 'spec' key of example/banutoo.json
        """

        assert machine_id not in self.root.master.machines or \
            self.root.master.machines[machine_id].machine.get_status() == "stopped", \
            "Machine must be stopped to modify"

        machine_spec = json.loads(machine_spec)
        self.root.master.add_machine(machine_id, machine_spec, write=True)
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


@cherrypy.popargs("disk_id")
class ZApiDisks():
    """
    Endpoint for managing disks
    """

    exposed = True

    def __init__(self, root):
        """
        Endpoint to modify disks. PUT and DELETE require the disk not be attached.
        TODO how to attach/detach?
        """
        self.root = root

    @cherrypy.tools.json_out()
    def GET(self, disk_id=None, summary=False):
        """
        Get a list of disks or a specific one if passed
        :param disk_id: task to retrieve
        """
        summary = summary in [True, 'True', 'true', 'yes', '1', 1]

        disks = {}
        for _disk_id, disk_spec in self.root.master.disks.items():
            disk = {"disk_id": _disk_id}
                       # "_status": machine_spec.machine.get_status()}  attached / detached ?
            # if not summary:
            #     machine.update({"machine_type": machine_spec.machine_type,
            #                     "spec": machine_spec.serialize()})
            disk.update({"spec": disk_spec.serialize()})

            disks[_disk_id] = disk
        if disk_id is not None:
            try:
                return [disks[disk_id]]
            except KeyError:
                raise cherrypy.HTTPError(status=404)
        else:
            return list(disks.values())

    @cherrypy.tools.json_out()
    def PUT(self, disk_id, disk_spec):
        """
        Create a new disk or update an existing disk
        :param disk_id: id of disk to create or modify
        'param disk_spec: json dictionary describing the disk. see the 'spec' key of example/ubuntu-root.json
        """
        disk_spec = json.loads(disk_spec)
        self.root.master.add_disk(disk_id, disk_spec, write=True)
        return disk_id

    def DELETE(self, disk_id):
        """
        Delete a disk. Raises 404 if no such disk exists. Raises error if disk is not idle (detached)
        :param disk_id: ID of disk to remove
        """
        self.root.master.remove_disk(disk_id)
        return disk_id

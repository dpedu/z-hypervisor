import logging

from zhypervisor.clients.qmachine import QMachine
from zhypervisor.clients.dockermachine import DockerMachine

MACHINETYPES = {"q": QMachine, "docker": DockerMachine}


class MachineSpec(object):
    """
    Represents a machine we may control
    """
    def __init__(self, master, machine_id, spec):
        """
        Initialize options and properties of the machine. More importantly, initialize the self.machine object which
        should be a subclass of zhypervisor.util.Machine.
        """
        logging.info("Initting machine %s", machine_id)
        self.master = master
        self.machine_id = machine_id

        self.properties = spec

        try:
            machine_type = MACHINETYPES[self.properties.get("type", None)]
        except KeyError:
            raise Exception("Unknown or missing machine type: {}".format(self.properties.get("type", None)))

        self.machine = machine_type(self)

    def start(self):
        """
        Start this machine (pass-through)
        """
        self.machine.block_respawns = False
        self.machine.start_machine()

    def stop(self):
        """
        Stop this machine
        """
        self.machine.block_respawns = True
        self.machine.stop_machine()

    def save(self):
        """
        Write the machine's config to disk
        """
        self.master.add_machine(self.machine_id, self.properties, write=True)

    def serialize(self):
        """
        Return a serializable form of this machine's specs
        """
        return self.properties

import logging

from zhypervisor.clients.qmachine import QMachine


class MachineSpec(object):
    """
    Represents a machine we may control
    """
    def __init__(self, master, machine_id, machine_type, spec):
        """
        Initialize options and properties of the machine. More importantly, initialize the self.machine object which
        should be a subclass of zhypervisor.util.Machine.
        """
        logging.info("Initting machine %s", machine_id)
        self.master = master
        self.machine_id = machine_id
        self.machine_type = machine_type

        self.options = spec["options"]
        self.properties = spec["properties"]

        # TODO replace if/else with better system
        if machine_type == "q":
            self.machine = QMachine(self)
        else:
            raise Exception("Unknown machine type: {}".format(machine_type))

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

    def serialize(self):
        """
        Return a serializable form of this machine's specs
        """
        return {"options": self.options,
                "properties": self.properties}

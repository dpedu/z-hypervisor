import logging

from zhypervisor.clients.qmachine import QMachine


class MachineSpec(object):
    def __init__(self, master, machine_id, machine_type, spec):
        logging.info("Initting machine %s", machine_id)
        self.master = master
        self.machine_id = machine_id
        self.machine_type = machine_type

        self.options = {}  # hypervisor-level stuff like Autostart
        self.properties = {}  # machine level stuff like processor count

        # TODO replace if/else with better system
        if machine_type == "q":
            self.machine = QMachine(self)
            self.options = spec["options"]
            self.properties = spec["properties"]
        else:
            raise Exception("Unknown machine type: {}".format(machine_type))

    def start(self):
        self.machine.start_machine()

    def stop(self):
        self.machine.block_respawns = True
        self.machine.stop_machine()

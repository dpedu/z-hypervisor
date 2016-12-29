
import os
import json
import signal
import logging
import argparse
import subprocess
from time import sleep
from concurrent.futures import ThreadPoolExecutor
from threading import Thread

from zhypervisor.logging import setup_logging
from zhypervisor.machine import MachineSpec
from zhypervisor.api.api import ZApi

from pprint import pprint


class ZHypervisorDaemon(object):
    def __init__(self, config):
        """
        Z Hypervisor main thread. Roles:
        - Load and start machines and API on init
        - Cleanup on shutdown
        - Committing changes to machines to disk
        - Primary interface to modify machines
        """
        self.config = config  # JSON config listing, mainly, datastore paths
        self.datastores = {}  # Mapping of datastore name -> objects
        self.machines = {}  # Mapping of machine name -> objects
        self.running = True

        # Set up datastores and use the default datastore for "State" storage
        self.init_datastores()
        self.state = ZConfig(self.datastores["default"])

        # start API
        self.api = ZApi(self)

        # Set up shutdown signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)   # ctrl-c
        signal.signal(signal.SIGTERM, self.signal_handler)  # sigterm

    def init_datastores(self):
        """
        Per datastore in the config, create a ZDataStore object
        """
        for name, info in self.config["datastores"].items():
            self.datastores[name] = ZDataStore(name, info["path"], info.get("init", False))

    def init_machines(self):
        """
        Per machine in the on-disk state, create a machine object
        """
        for machine_info in self.state.get_machines():
            machine_id = machine_info["machine_id"]
            self.add_machine(machine_id, machine_info["machine_type"], machine_info["spec"])

    def signal_handler(self, signum, frame):
        """
        Handle signals sent to the daemon. On any, exit.
        """
        logging.critical("Got signal {}".format(signum))
        self.stop()

    def run(self):
        """
        Main loop of the daemon. Sets up & starts machines, runs api, and waits.
        """
        self.init_machines()
        self.api.run()

    def stop(self):
        """
        SHut down the hypervisor. Stop the API then shut down machines
        """
        self.running = False
        self.api.stop()
        with ThreadPoolExecutor(10) as pool:
            for machine_id in self.machines.keys():
                pool.submit(self.forceful_stop, machine_id)
        # Sequential shutdown code below is easier to debug
        # for machine_id in self.machines.keys():
        #     self.forceful_stop(machine_id)

    # Below here are methods external forces may use to manipulate disks

    def create_disk(self, datastore, name, fmt, size=None):
        """
        Create a disk. Disks represent arbitrary storage
        @TODO support formats passed by runnable modules
        :param datastore: datastore to store the disk in
        :param name: name for the disk
        :param size: size of the disk, in mb, if applicable
        :param format: format of the disk
        """
        disk_path = self.datastores[datastore].get_filepath(name)
        assert not os.path.exists(disk_path), "Disk already exists!"
        img_args = ["qemu-img", "create", "-f", fmt, disk_path, "{}M".format(int(size))]
        logging.info("Creating disk with: %s", str(img_args))
        subprocess.check_call(img_args)

    # Below here are methods external forces may use to manipulate machines

    def add_machine(self, machine_id, machine_type, machine_spec, write=False):
        """
        Create or update a machine.
        :param machine_id: alphanumeric id of machine to modify/create
        :param machine_type: runnable type e.g. "q"
        :param machine_spec: dictionary of machine options - see example/ubuntu.json
        :param write: commit machinge changes to on-disk state
        """
        # Find / create the machine
        if machine_id in self.machines:
            machine = self.machines[machine_id]
            machine.options = machine_spec["options"]
            machine.properties = machine_spec["properties"]
        else:
            machine = MachineSpec(self, machine_id, machine_type, machine_spec)
            self.machines[machine_id] = machine

        # Update if necessary
        if write:
            self.state.write_machine(machine_id, machine_type, machine_spec)

        # Launch if machine is an autostarted machine
        if machine.options.get("autostart", False) and machine.machine.get_status() == "stopped":
            machine.start()

    def forceful_stop(self, machine_id, timeout=10):  # make this timeout longer?
        """
        Gracefully stop a machine by asking it nicely, waiting some time, then forcefully killing it.
        """
        machine_spec = self.machines[machine_id]
        nice_stop = Thread(target=machine_spec.stop)
        nice_stop.start()
        nice_stop.join(timeout)

        if nice_stop.is_alive():
            logging.error("%s did not respond in %s seconds, killing", machine_id, timeout)
            machine_spec.machine.kill_machine()

    def remove_machine(self, machine_id):
        """
        Remove a stopped machine from the system. The machine should already be stopped.
        """
        assert self.machines[machine_id].machine.get_status() == "stopped"
        self.state.remove_machine(machine_id)
        del self.machines[machine_id]


class ZDataStore(object):
    """
    Helper module representing a data storage location somewhere on disk
    """
    def __init__(self, name, root_path, init_ok=False):
        self.name = name
        self.root_path = root_path
        os.makedirs(self.root_path, exist_ok=True)
        try:
            metainfo_path = self.get_filepath(".datastore.json")
            assert os.path.exists(metainfo_path), "Datastore missing or not initialized! " \
                                                  "File not found: {}".format(metainfo_path)
        except:
            if init_ok:
                with open(metainfo_path, "w") as f:
                    json.dump({}, f)
            else:
                raise
        logging.info("Initialized datastore %s at %s", name, self.root_path)

    def get_filepath(self, *paths):
        return os.path.join(self.root_path, *paths)


class ZConfig(object):
    """
    The Z Hypervisor daemon's interface to the on-disk config
    """
    def __init__(self, datastore):
        self.datastore = datastore

        self.machine_data_dir = self.datastore.get_filepath("machines")

        for d in [self.machine_data_dir]:
            os.makedirs(d, exist_ok=True)

    def get_machines(self):
        """
        Return config of all machines on disk
        """
        machines = []
        logging.info("Looking for machines in {}".format(self.machine_data_dir))
        for mach_name in os.listdir(self.machine_data_dir):
            with open(os.path.join(self.machine_data_dir, mach_name), "r") as f:
                machines.append(json.load(f))
        return machines

    def write_machine(self, machine_id, machine_type, machine_spec):
        """
        Write a machine's config to the disk. Params similar to elsewhere.
        """
        with open(os.path.join(self.machine_data_dir, "{}.json".format(machine_id)), "w") as f:
            json.dump({"machine_id": machine_id,
                       "machine_type": machine_type,
                       "spec": machine_spec}, f, indent=4)

    def write_machine_o(self, machine_obj):
        """
        Similar to write_machine, but accepts a MachineSpec object
        """
        self.write_machine(machine_obj.machine_id, machine_obj.machine_type, machine_obj.serialize())

    def remove_machine(self, machine_id):
        """
        Remove a machine from the on disk state
        """
        json_path = os.path.join(self.machine_data_dir, "{}.json".format(machine_id))
        os.unlink(json_path)


def main():
    setup_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default="/etc/zd.json", help="Config file path")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        logging.warning("Config does not exist, attempting to write default config")
        with open(args.config, "w") as f:
            json.dump({"nodename": "examplenode",
                       "access": [("root", "toor", 0)],
                       "state": "/opt/datastore/state/",
                       "datastores": {
                           "default": {
                               "path": "/opt/z/datastore/machines/"
                           }
                       }}, f, indent=4)
        return

    with open(args.config) as f:
        config = json.load(f)

    z = ZHypervisorDaemon(config)
    z.run()
    print("Z has been shut down")

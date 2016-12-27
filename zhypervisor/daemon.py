
import os
import json
import signal
import logging
import argparse
from time import sleep
from concurrent.futures import ThreadPoolExecutor

from zhypervisor.logging import setup_logging
from zhypervisor.machine import MachineSpec

from pprint import pprint


class ZHypervisorDaemon(object):
    def __init__(self, config):
        self.config = config
        self.datastores = {}
        self.machines = {}
        self.running = True

        self.init_datastores()
        self.state = ZConfig(self.datastores["default"])

        signal.signal(signal.SIGINT, self.signal_handler)   # ctrl-c
        signal.signal(signal.SIGTERM, self.signal_handler)  # sigterm

    def init_datastores(self):
        for name, info in self.config["datastores"].items():
            self.datastores[name] = ZDataStore(name, info["path"], info.get("init", False))

    def init_machines(self):
        for machine_info in self.state.get_machines():
            machine_id = machine_info["id"]
            self.add_machine(machine_id, machine_info["type"], machine_info["spec"])

    def add_machine(self, machine_id, machine_type, machine_spec):
        machine = MachineSpec(self, machine_id, machine_type, machine_spec)
        self.machines[machine_id] = machine
        if machine.options.get("autostart", False):
            machine.start()

    def signal_handler(self, signum, frame):
        logging.critical("Got signal {}".format(signum))
        self.stop()

    def run(self):
        # launch machines
        self.init_machines()

        # start API
        # TODO

        # Wait?
        while self.running:
            sleep(1)

    def stop(self):
        self.running = False

        with ThreadPoolExecutor(10) as pool:
            for machine_id, machine in self.machines.items():
                pool.submit(machine.stop)


class ZDataStore(object):
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
    def __init__(self, datastore):
        self.datastore = datastore

        self.machine_data_dir = self.datastore.get_filepath("machines")

        for d in [self.machine_data_dir]:
            os.makedirs(d, exist_ok=True)

    def get_machines(self):
        machines = []
        logging.info("Looking for machines in {}".format(self.machine_data_dir))
        for mach_name in os.listdir(self.machine_data_dir):
            with open(os.path.join(self.machine_data_dir, mach_name), "r") as f:
                machines.append(json.load(f))
        return machines


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
                               "path": "/opt/datastore/machines/"
                           }
                       }}, f, indent=4)
        return

    with open(args.config) as f:
        config = json.load(f)

    z = ZHypervisorDaemon(config)
    z.run()


import os
from random import randint


class TapDevice(object):
    """
    Utility class - adds/removes a tap device on the linux system. Can be used as a context manager.
    """
    def __init__(self):
        self.num = randint(0, 100000)

    def create(self):
        os.system("ip tuntap add name {} mode tap".format(self))

    def destroy(self):
        os.system("ip link delete {}".format(self))

    def __str__(self):
        return "tap{}".format(self.num)

    def __enter__(self):
        self.create()
        return str(self)

    def __exit__(self, type, value, traceback):
        self.destroy()


class Machine(object):
    """
    All runnable types should subclass this
    """
    def __init__(self, machine_spec):
        self.spec = machine_spec

    def run_machine(self):
        """
        Run the machine and block until it exits (or was killed)
        """
        raise NotImplemented()

    def stop_machine(self):
        """
        Ask the machine to stop nicely
        """
        raise NotImplemented()

    def kill_machine(self):
        """
        Stop the machine, brutally
        """
        raise NotImplemented()

    def get_status(self):
        """
        Get the machine's status (return one of "running" or "stopped")
        """
        raise NotImplemented()

    def get_datastore_path(self, datastore_name, *paths):
        """
        Resolve the filesystem path for a path in the given datastore
        """
        return self.spec.master.datastores.get(datastore_name).get_filepath(*paths)

import os
import logging
import subprocess
from time import sleep
from threading import Thread
from zhypervisor.util import ZDisk
from zhypervisor.util import Machine


class DockerMachine(Machine):
    machine_type = "docker"

    def __init__(self, spec):
        Machine.__init__(self, spec)
        self.proc = None
        self.block_respawns = False

    def get_status(self):
        """
        Return string "stopped" or "running" depending on machine status
        """
        return "stopped" if self.proc is None else "running"

    def start_machine(self):
        """
        If needed, launch the machine.
        """
        if self.proc:
            raise Exception("Machine already running!")
        else:
            docker_args = self.get_args()
            logging.info("spawning docker with: {}".format(' '.join(docker_args)))
            sleep(1)  # anti-spin
            self.proc = subprocess.Popen(docker_args, preexec_fn=lambda: os.setpgrp())
            # TODO handle stdout/err - stream to logs?
            Thread(target=self.wait_on_exit, args=[self.proc]).start()

    def wait_on_exit(self, proc):
        """
        Listener used by above start_machine to restart the machine if the machine exits
        """
        proc.wait()
        logging.info("docker process has exited")
        self.proc = None
        if not self.block_respawns and self.spec.properties.get("respawn", False):
            self.start_machine()

    def stop_machine(self):
        """
        Send the powerdown signal to the running machine
        """
        if self.proc:
            logging.info("stopping machine %s", self.spec.machine_id)
            subprocess.check_call(["docker", "stop", self.spec.machine_id])
            self.proc.wait()
            self.proc = None

    def kill_machine(self):
        """
        Forcefully kill the running machine
        """
        print("Terminating {}".format(self.proc))
        if self.proc:
            subprocess.check_call(["docker", "kill", self.spec.machine_id])
            try:
                self.proc.wait(5)
            except subprocess.TimeoutError:
                self.proc.kill()
            self.proc.wait()
            self.proc = None

    def get_args(self):
        """
        Assemble the full argv array that will be executed for this machine
        """
        argv = ['docker', 'run', '--rm', '--name', self.spec.machine_id,
                '--hostname', self.spec.properties.get("hostname", self.spec.machine_id)]

        for hostport, containerport in self.spec.properties.get("ports", []):
            argv.append("-p")
            argv.append("{}:{}".format(int(hostport), int(containerport)))

        for volume in self.spec.properties.get("volumes", []):
            disk_ob = self.spec.master.disks[volume["disk"]]

            volpath = disk_ob.get_path()
            argv.append("-v")
            argv.append("{}:{}".format(volpath, volume.get("mountpoint")))

        if self.spec.properties.get("stopsignal", False):
            argv += ['--stop-signal', int(self.spec.properties.get("stopsignal"))]

        argv += ['--stop-timeout', int(self.spec.properties.get("timeout", 25))]

        argv.append("{}".format(self.spec.properties.get("image")))
        if self.spec.properties.get("cmd", False):
            argv.append("{}".format(self.spec.properties.get("cmd")))

        return [str(arg) for arg in argv]


class DockerDisk(ZDisk):

    def validate(self):
        pass
        # alphanumeric only? underscores?

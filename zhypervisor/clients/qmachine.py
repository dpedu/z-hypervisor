import os
import logging
import subprocess
from time import sleep
from threading import Thread

from zhypervisor.util import TapDevice, Machine
from zhypervisor.util import ZDisk


class QMachine(Machine):
    machine_type = "q"

    def __init__(self, spec):
        Machine.__init__(self, spec)
        self.proc = None
        self.tap = TapDevice()
        self.block_respawns = False
        # TODO validate specs

    def get_status(self):
        """
        Return string "stopped" or "running" depending on machine status
        @TODO machine status consts
        """
        return "stopped" if self.proc is None else "running"

    def start_machine(self):
        """
        If needed, launch the machine.
        """
        if self.proc:
            raise Exception("Machine already running!")
        else:
            qemu_args = self.get_args(tap=str(self.tap))
            logging.info("spawning qemu with: {}".format(' '.join(qemu_args)))
            sleep(1)  # anti-spin
            self.proc = subprocess.Popen(qemu_args, preexec_fn=lambda: os.setpgrp(), stdin=subprocess.PIPE)
            # TODO handle stdout/err - stream to logs?
            Thread(target=self.wait_on_exit, args=[self.proc]).start()

    def wait_on_exit(self, proc):
        """
        Listener used by above start_machine to restart the machine if the machine exits
        """
        proc.wait()
        logging.info("qemu process has exited")
        self.proc = None
        if not self.block_respawns and self.spec.properties.get("respawn", False):
            self.start_machine()

    def stop_machine(self):
        """
        Send the powerdown signal to the running machine
        """
        if self.proc:
            logging.info("stopping machine %s", self.spec.machine_id)
            self.proc.stdin.write(b"system_powerdown\n")
            self.proc.stdin.flush()
            self.proc.wait()
            self.proc = None

    def kill_machine(self):
        """
        Forcefully kill the running machine
        """
        print("Terminating {}".format(self.proc))
        if self.proc:
            self.proc.terminate()
            self.proc.wait()
            self.proc = None

    def get_args(self, tap):
        """
        Assemble the full argv array that will be executed for this machine
        """
        argv = ['qemu-system-x86_64']
        argv += self.get_args_system()
        argv += self.get_args_drives()
        argv += self.get_args_network(tap)
        return argv

    def get_args_system(self):
        """
        Return system-related args:
        - Qemu meta args
        - CPU core settings
        - Mem amnt
        - Boot device
        """
        args = ["-monitor", "stdio", "-machine", "accel=kvm", "-smp"]
        args.append("cpus={}".format(self.spec.properties.get("cores", 1)))  # why doesn't this work: ,cores={}
        args.append("-m")
        args.append(str(self.spec.properties.get("mem", 256)))
        args.append("-boot")
        args.append("cd")
        if self.spec.properties.get("vnc", False):
            args.append("-vnc")
            assert type(self.spec.properties.get("vnc")) == int, "VNC port should be an integer"
            args.append(":{}".format(self.spec.properties.get("vnc")))
        return args

    def get_args_network(self, tap_name):
        """
        Return network related qemu args
        """
        args = []
        for iface in self.spec.properties.get("netifaces"):
            iface_type = iface.get("type")
            iface_args = {"type": iface_type}

            if iface_type == "tap":
                if "ifname" in iface:
                    iface_args["ifname"] = iface.get("ifname")
                iface_args["script"] = "/root/zhypervisor/testenv/bin/zd_ifup"  # TODO don't hard code
                iface_args["downscript"] = "no"
            else:
                iface_args.update(iface)

            args.append("-net")
            args.append(QMachine.format_args(iface_args))
        return args

        # return ['-net', 'nic,vlan=0,model=e1000,macaddr=82:25:60:41:D5:97',
        #        '-net', 'tap,ifname={},script=if_up.sh,downscript=no'.format(tap_name)]

    def get_args_drives(self):
        """
        Inspect props.drives expecting a format like:  {"file": "/tmp/ubuntu.qcow2", "index": 0, "if": "virtio"}
        """
        args = []
        for attached_drive in self.spec.properties.get("drives", []):
            args.append("-drive")

            disk_ob = self.spec.master.disks[attached_drive["disk"]]

            drive_args = {"file": disk_ob.get_path()}

            for option in ["if", "index", "media"]:
                if option in attached_drive:
                    drive_args[option] = attached_drive[option]

            args.append(QMachine.format_args((drive_args)))

        return args

    @staticmethod
    def format_args(d):
        """
        Given a dictionary like: {"file": "/dev/zd0", "index": 0, "if", "virtio"}
        Return a string like: file=/dev/zd0,index=0,if=virtio
        """
        args = []
        for item, value in d.items():
            if item == "type":
                args.insert(0, value)
            else:
                args.append("{}={}".format(item, value))
        if not args:
            return None
        return ','.join(args)


class QDisk(ZDisk):

    def init(self):
        """
        Create a QEMU-formatted virtual disk
        """
        disk_path = self.get_path()
        assert not os.path.exists(disk_path), "Disk already exists!"
        img_args = ["qemu-img", "create", "-f", self.properties["fmt"], disk_path, "{}M".format(int(self.properties["size"]))]
        logging.info("Creating disk with: %s", str(img_args))
        subprocess.check_call(img_args)

    def validate(self):
        assert self.disk_id.endswith(".bin"), "QDisks names must end with '.bin'"

    def delete(self):
        os.unlink(self.get_path())


class IsoDisk(ZDisk):
    pass
    # TODO make this do more nothing

    def validate(self):
        assert self.disk_id.endswith(".iso"), "IsoDisk names must end with '.iso'"

    def init(self):
        assert os.path.exists(self.get_path()), "ISO must already exist!"

    def delete(self):
        pass

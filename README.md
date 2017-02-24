Z Hypervisor
============

A minimal hypervisor based on QEMU, with HTTP API


Requirements
============

- kvm kernel module
- Qemu (Specifically, qemu-system-x86_64)
- brctl (part of bridge-utils on Ubuntu)
- an ethernet bridge named br0
- it must run as root


Install
=======

- Check out this repo, install using pip3
- Create a config (see example/zd.json)
- Run `zd -c|--config /path/to/zd.json`


HTTP API
========

*GET /api/v1/machine/:id/start*

    Start a machine given its id

*GET /api/v1/machine/:id/stop*

    Stop a machine given its id

*GET /api/v1/machine/:id/restart*

    Stop a machine given its id

*GET /api/v1/machine/:id*

    Get the description of a machine or all machines if no id passed

*PUT /api/v1/machine/:id*

    Create a new machine or update an existing machine. Params:
    - machine_id: alphanumeric name for the machine
    - machine_spec: serialized json object describing the machine. See the 'spec' key of example/ubuntu.json

*DELETE /api/v1/machine/:id*

    Delete a machine give its id

*GET /api/v1/machine/:id/property/:property*

    Get the current value of a machine's property

*PUT /api/v1/machine/:id/property/:property*

    Create or update a machine's property. Params:
    - machine_id: alphanumeric name for the name
    - property: name of the property to modify or create
    - value: serialized json object to set as the value

*DELETE /api/v1/machine/:id/property/:property*

    Remove a property from a machine

*GET /api/v1/disk/:id*

    List all disks or a specific disk if passed

*PUT /api/v1/disk/:id*

    Create a storate disk to use with machines. Params:
    - disk_spec: serialized json object describing the disk. See the 'spec' key of example/ubuntu-root.json and example/ubuntu-iso.json

*DELETE /api/v1/disk/:id*

    Delete a disk by ID

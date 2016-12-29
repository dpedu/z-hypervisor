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

*GET /api/v1/create_disk*

    Create a storate disk to use with machines. Params:
    - datastore: datastore name such as 'default'
    - name: arbitrary disk name like 'ubuntu-root.bin'
    - size: size in megabytes
    - fmt: format, raw or qcow2

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
    - machine_id: alphanumeric name for the name
    - machine_type: type of virtualization to run the machine with
    - machine_spec: serialized json object describing the machine. See the 'spec' key of example/ubuntu.json

*DELETE /api/v1/machine/:id*

    Delete a machine give its id


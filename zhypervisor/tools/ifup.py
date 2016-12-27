#!/usr/bin/env python3

import sys
import logging
from subprocess import check_call

from zhypervisor.logging import setup_logging


def main():
    setup_logging()
    _, tap_name = sys.argv
    logging.info("Enabling interface %s...", tap_name)
    check_call(["brctl", "addif", "br0", tap_name])
    check_call(["ifconfig", tap_name, "up"])
    logging.info("Enabled interface %s", tap_name)

if __name__ == '__main__':
    main()

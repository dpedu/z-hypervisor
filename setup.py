#!/usr/bin/env python3

from setuptools import setup
from zhypervisor import __version__


setup(name='zhypervisor',
      version=__version__,
      description='python-based x86 hypervisor using qemu',
      url='http://gitlab.xmopx.net/dave/zhypervisor',
      author='dpedu',
      author_email='dave@davepedu.com',
      packages=['zhypervisor', 'zhypervisor.clients', 'zhypervisor.tools'],
      entry_points={'console_scripts': ['zd = zhypervisor.daemon:main',
                                        'zd_ifup = zhypervisor.tools.ifup:main']},
      zip_safe=False)

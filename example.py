#!/usr/bin/env python3

import os
import pexpect

import gdb

# this supports .interact(), but is much slower...
# if you're doing a large automated task, then use the default
pexpect_spawn = pexpect.spawn

# get a log file...
f = open('out.log', 'wb')

# get an interface to gdb
x = gdb.Driver(spawn=pexpect_spawn, logfile=f)

# setup the sysroot and shared library search path
x.set_sysroot('./sysroot/')
solib_search_paths = [
    './sysroot/lib/',
    '/opt/my_bsp/yocto/build/tmp/sysroots/my_sysroot/lib/'
]
x.set_solib_search_path(solib_search_paths)

# pick the binary and core
x.load_file('./bin')
x.load_core('./core')

# capture where we started...
start_point = x.get_location()

# goto main(), and get the source path
x.set_location_main()
x.set_current_source_dir('./src/', 'my/project/path')

# print a thread summary
#threads = x.print_threads_summary()

# allow the user to interact directly with gdb
x.interact(start_point)

## gdb_driver

This is a simple python wrapper for `gdb`. The original intention was to automate the setup of the debug environment, before handing over to the user to interact with `gdb`, hence the use of `pexpect`.

It can additionally provide very effective automation for inspecting complex core dumps.

### Usage

To make use of the `example.py`, simply create a set of symlinks as below (or edit the file):

* `bin` &rarr; your executable
* `core` &rarr; the core dump produced by the system
* `src` &rarr; the root of your source directory
* `sysroot` &rarr; the root of the sysroot in use

You may also need to edit the call to `set_current_source_dir()` so that the source code can be correctly located.

### Automation

The following example can be used to analyse the core dump and print a list of threads that are stuck at any given point. This is particularly useful if a number of threads are locked on a semaphore or mutex.

    thread_summary = {}
    for thread in x.get_thread_summary():
        sig = thread['stack'][0]['signature']
        if sig not in thread_summary:
            thread_summary[sig] = []
        thread_summary[sig].append(thread)

    for sig, threads in sorted(thread_summary.items(), key=lambda i: len(i[1])):
        print(sig, 'x%d' % ( len(threads) ))
        for thread in threads:
            print('    ', thread['thread_num'], thread['tid'], thread['stack'][-1]['signature'])

Example Output:

	nanosleep() x1
	     1 576 main(argc=1, argv=0x7ebc1de4)
	sem_timedwait(sem=0x9851f4, abstime=0x64c55dbc) x1
	     8 591 _bep_thread(info=0x985198)
	[...]
	__GI___pthread_mutex_lock(mutex=0x65c65dd4) x31
	     214 32020 handle_func_lt(INFO=0x5e703d18)
	     213 32028 handle_func_lt(INFO=0x5e7039a8)
	     210 32041 handle_func_lt(INFO=0x5e703af0)
	     208 32055 handle_func_lt(INFO=0x5e7026e0)
	[...]
	__new_sem_wait(sem=0x76f42ca0 <db+28>) x136
	     212 28253 handle_func_lt(INFO=0x59b02680)
	     211 28014 handle_func_lt(INFO=0x59b01fe0)
	     209 27762 handle_func_lt(INFO=0x59b01dd0)
	     207 25458 handle_func_lt(INFO=0x59b02620)
	[...]

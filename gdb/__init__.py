#!/bin/false

import sys, re
import pexpect
from pexpect import popen_spawn

class Driver:
    """ setup
            cmd: the command to run for a gdb instance. if you're doing
                 cross-target work, then you will need to provide the
                 appropriate version of gdb for your target
            spawn: the pexpect 'spawn' to call
                   pexpect.popen_spawn.PopenSpawn offers better performance,
                       but it is not possible to interact() via it
                   pexpect.spawn is significantly slower, but it _is_ possible
                       to interact() via it
            logfile: passed to pexepct, the session will be logged here """
    def __init__(self, cmd='gdb', spawn=pexpect.popen_spawn.PopenSpawn, logfile=None):
        self.cmd = cmd
        self.spawn = spawn

        # we're also going to use these complex regexs a few times, so just keep them once
        self.relib = {}
        self.relib['bt'] = re.compile('^#(?P<frame_num>[0-9]+) +(?:0x[0-9a-fA-F]+ in)? (?P<function_name>[^ ]+) \((?P<function_args>[^\)]*)\)(?: at (?P<filename>[^:]+):(?P<line>[0-9]+))?(?: from (?P<libname>.+))?', re.MULTILINE)
        self.relib['threads'] = re.compile('^\*? +(?P<thread_num>[0-9]+) +(?:LWP )?(?P<thread_id>[0-9]+)', re.MULTILINE)

        # some function/file tuples that we don't want to see
        self.invisible_ff = [] #   function name                filename
        self.invisible_ff.append(( 'do_futex_wait',             'sem_wait.c'       ))
        self.invisible_ff.append(( 'do_futex_timed_wait',       'sem_timedwait.c'  ))
        self.invisible_ff.append(( '__lll_lock_wait',           'lowlevellock.c'   ))
        self.invisible_ff.append(( '??',                        'clone.S'          ))
        self.invisible_ff.append(( 'start_thread',              'pthread_create.c' ))
        self.invisible_ff.append(( '__nptl_deallocate_tsd',     'pthread_create.c' ))

        # kick off gdb
        self.xpt = spawn(cmd, logfile=logfile)
        self.xpt.linesep = b'\n'

        # we're going to be using the prompt regex quite a bit, so compile it
        self.prompt = self.xpt.compile_pattern_list(b'\(gdb\) ')

        # wait for an initial prompt
        self._wait_prompt()

        # set it up for us
        self._setup_gdb()

    """ use pexpect to wait for the next prompt
        capture any lines from the previous output, cleanup, and return """
    def _wait_prompt(self):
        self.xpt.expect_list(self.prompt)
        lines_dirty = self.xpt.before.decode('utf-8')
        # yucky, yucky, yucky, yucky...
        lines_clean = '\n'.join(lines_dirty.split('\r\n'))
        self.lines = lines_clean
        return lines_clean

    """ call pexpect's sendline() with the given payload """
    def _send_line(self, line):
        self.xpt.sendline(line)

    """ issue the command, and return the command's output """
    def _send_cmd(self, command):
        self._send_line(command)
        return self._wait_prompt()

    """ perform some initial setup:
            prevent line wrapping
            prevent paging """
    def _setup_gdb(self):
        # disable line wrapping & paging
        self._send_cmd('set width 0')
        self._send_cmd('set height 0')

    """ issue the "set solib-search-path" gdb command
            path_list: a list of paths to search! """
    def set_solib_search_path(self, path_list=[]):
        path_var = ':'.join(path_list)
        self._send_cmd('set solib-search-path %s' % ( path_var ))

    """ issue the "set sysroot" gdb command
            sysroot: The path to the alternate system root """
    def set_sysroot(self, sysroot):
        self._send_cmd('set sysroot %s' % ( sysroot ))

    """ issue the "show sysroot" gdb command, and return its value """
    def get_sysroot(self):
        lines = self._send_cmd('show sysroot')
        match = re.search('^The current system root is "(?P<sysroot>[^"]*)".', lines, re.MULTILINE)
        return match.group('sysroot')

    """ issue the "file" gdb command
            filepath: the path to the program to be debuggeed """
    def load_file(self, filepath):
        self._send_cmd('file %s' % ( filepath ))

    """ issue the "core" gdb command
            corepath: the path to the coredump, for examining memory
                      and registers """
    def load_core(self, corepath):
        self._send_cmd('core %s' % ( corepath ))

    """ issue the "info inferior gdb command, and extract the process' ID """
    def get_pid(self):
        lines = self._send_cmd('info inferior')
        match = re.search('^\*? *[0-9]+ *process (?P<process_id>[0-9]+)', lines, re.MULTILINE)
        return int(match.group('process_id'))

    """ issue the "frame" gdb command, and return the selected frame's index """
    def get_frame(self):
        lines = self._send_cmd('frame')
        match = re.search('^#(?P<frame_num>[0-9]+)', lines, re.MULTILINE)
        return int(match.group('frame_num'))

    """ issue the "frame" gdb command to set the selected frame """
    def set_frame(self, frame):
        lines = self._send_cmd('frame %d' % ( frame ))
        match = re.search('^#(?P<frame_num>[0-9]+)', lines, re.MULTILINE)
        if frame != int(match.group('frame_num')):
            raise Exception('failed to switch frame...')

    """ issue the "thread" gdb command, and return the selected thread's index """
    def get_thread(self):
        lines = self._send_cmd('thread')
        match = re.search('^\[Current thread is (?P<thread_id>[0-9]+)', lines, re.MULTILINE)
        return int(match.group('thread_id'))

    """ issue the "thread" gdb command to set the selected thread """
    def set_thread(self, thread):
        lines = self._send_cmd('thread %d' % ( thread ))
        match = re.search('^\[Switching to thread (?P<thread_id>[0-9]+)', lines, re.MULTILINE)
        if thread != int(match.group('thread_id')):
            raise Exception('failed to switch thread...')

    """ returns a ( <thread_index> , <frame_index> ) tuple describing the current state """
    def get_location(self):
        return ( self.get_thread(), self.get_frame() )

    """ takes a ( <thread_index> , <frame_index> ) tuple, and apply it """
    def set_location(self, location):
        self.set_thread(location[0])
        self.set_frame(location[1])

    """ locate the 'main' thread (that with TID == PID) and go to it
        returns a ( <thread_index> , <frame_index> ) as above """
    def set_location_main(self):
        pid = self.get_pid()
        thread_list = self.get_thread_list()
        thread_num = [ x['thread_num'] for x in thread_list if x['tid'] == pid ][0]
        self.set_thread(thread_num)
        main_frame = self.get_backtrace()[-1]
        if main_frame['function_name'] != 'main':
            raise Exception('thread\'s top isn\'t main()... %s' % ( main_frame['function_name'] ))

        frame_num = main_frame['frame_num']
        self.set_frame(frame_num)

        return ( thread_num, frame_num )

    """ issue the "bt" gdb command
        returns a list of dicts describing the backtrace """
    def get_backtrace(self):
        lines = self._send_cmd('bt')

        stack = []
        for match in [ x.groupdict() for x in self.relib['bt'].finditer(lines) ]:
            match['frame_num'] = int(match['frame_num'])

            if match['line'] is not None:
                match['line'] = int(match['line'])

            stack.append(match)

        return stack

    """ issue the "info source" gdb command
        returns the current source directory """
    def get_current_source_dir(self):
        lines = self._send_cmd('info source')
        match = re.search('^Compilation directory is (?P<source_dir>.*)$', lines, re.MULTILINE)
        return match.group('source_dir')

    """ setup an alias for the program's compilation directory
        e.g: application was built in:
                 /home/attie/this_project/my_app/src
             sources now available at:
                 /home/attie/debug/that_project/my_app/src

             give:
                 live_source_dir = "/home/attie/debug/that_project"
                 matching_suffix = "my_app/src"   """
    def set_current_source_dir(self, live_source_dir, matching_suffix=None):
        compiled_source_dir = self.get_current_source_dir()
        if matching_suffix is not None:
            if not compiled_source_dir.endswith(matching_suffix):
                raise Exception('expected matching suffix [%s] vs. [%s]...' % ( compiled_source_dir, matching_suffix ))
            compiled_source_dir = compiled_source_dir[:-len(matching_suffix)]
        self.set_source_subpath(compiled_source_dir, live_source_dir)

    """ issue the "set sub" gdb command
        sets up a substitute path used to locate source files """
    def set_source_subpath(self, compiled_root, live_root):
        self._send_cmd('set sub %s %s' % ( compiled_root, live_root ))

    """ get things ready, and then call pexpect's interact()
        location: optionally a ( <thread_index> , <frame_index> ) tuple

        avoids any repeating commands by issueing "python True"
        this also has the benefit of producing a prompt which is sent to the user
        rather than capture by pexpect """
    def _interact(self, location=None):
        if location is not None:
            self.set_location(location)
        else:
            location = self.get_location()
        print('--> Thread %d, Frame %d...' % ( location[0], location[1] ))
        self.xpt.sendline('python True')
        self.xpt.expect('python True')
        try:
            self.xpt.interact()
        except OSError as e:
            print('Oh no... %s' % ( repr(e) ))
        except pexpect.exceptions.EOF as e:
            print('Oh no... %s' % ( repr(e) ))

    """ a verbose way to call _interact() """
    def interact(self, location=None):
        print('--== Over to you... ==--')
        self._interact(location)

    """ call _interact() for each thread in the process """
    def interact_each_thread(self, thread_list=None):
        if thread_list is None:
            thread_list = self.get_thread_list()

        thread_list = list(thread_list)

        for i in range(len(thread_list) - 1, -1, -1):
            thread = thread_list[i]
            self.set_thread(thread['thread_num'])
            print('--== Over to you... (tid=%d) ==--' % ( thread['tid'] ))
            self._interact()

    """ generate a list of threads, each as a dict """
    def get_thread_list(self):
        lines = self._send_cmd('info threads')
        for match in [ x.groupdict() for x in self.relib['threads'].finditer(lines) ]:
            thread_info = {}
            thread_info['thread_num'] = int(match['thread_num'])
            thread_info['tid']  = int(match['thread_id'])
            yield thread_info

    """ generate a detailled summary of all thread, each as a dict """
    def get_thread_summary(self):
        for thread_info in self.get_thread_list():
            self._send_cmd('thread %d' % ( thread_info['thread_num'] ))

            thread_info['stack'] = self.get_backtrace()
            thread_info['stack_start'] = self.prune_stack_front(thread_info['stack'])
            thread_info['stack_end'] = self.prune_stack_back(thread_info['stack'])
            self.populate_stack_signatures(thread_info['stack'])

            yield thread_info

    """ print a detailed summary of all threads
        thread_list: if None, will tall get_thread_summary()
                     else,    will use provided list
        f: write the summary to this file """
    def print_threads_summary(self, thread_list=None, f=sys.stdout):
        if thread_list is None:
            thread_list = self.get_thread_summary()

        thread_list = list(thread_list)

        # here are the columns
        cols = [
            ( 'Num',              "thread['thread_num']"             ),
            ( 'Thread Id',        "thread['tid']"                    ),
            ( 'Start Function',   "thread['stack'][-1]['signature']" ),
            ( 'Current Function', "thread['stack'][0]['signature']"  ),
        ]

        # first step through to figure out how wide each column needs to be
        col_widths = [ 0 ] * len(cols)
        # - headings...
        for i, col in enumerate(cols):
            if len(col[0]) > col_widths[i]:
                col_widths[i] = len(col[0])
        # - and content...
        for thread in thread_list:
            for i, col in enumerate(cols):
                t = str(eval(col[1]))
                if len(t) > col_widths[i]:
                    col_widths[i] = len(t)

        # then step through and print out the table
        # - headings...
        for i, col in enumerate(cols):
            f.write(col[0].ljust(col_widths[i], ' '))
            f.write('\t')
        f.write('\n')
        # - and content...
        for i in range(len(thread_list) - 1, -1, -1):
            thread = thread_list[i]
            for i, col in enumerate(cols):
                t = str(eval(col[1]))
                t = t.ljust(col_widths[i], ' ')
                f.write(t)
                f.write('\t')
            f.write('\n')

    """ prune any 'invisible function/file' layers of the stack
        stack: a stack frame, laid out as returned from get_backtrace()
        index: the index to interrogate, and possibly remove and item from """
    def prune_stack(self, stack, index):
        pop_count = 0

        while len(stack) > 1:
            function_name = stack[index]['function_name']
            filename = stack[index]['filename']

            if filename is not None:
                filename = filename.split('/')[-1]

            if ( function_name, filename ) not in self.invisible_ff:
                break

            stack.pop(index)
            pop_count += 1

        return pop_count

    """ call prune_stack(), focussing at the 'front' """
    def prune_stack_front(self, stack):
        # snip off items from the front of the stack
        return self.prune_stack(stack, 0)

    """ call prune_stack(), focussing at the 'back' """
    def prune_stack_back(self, stack):
        # snip off items from the back of the stack
        return self.prune_stack(stack, -1)

    """ produce a frame's signature
        typically <function_name>(<function_args>)
        can be adapted to provide more relevant information for certain functions """
    def populate_stack_frame_signature(self, frame):
        function_args = frame['function_args']
        frame['signature'] = '%s(%s)' % ( frame['function_name'], function_args )
        
    """ call populate_stack_frame_signature() for each frame in stack """
    def populate_stack_signatures(self, stack):
        for frame in stack:
            self.populate_stack_frame_signature(frame)

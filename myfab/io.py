from __future__ import with_statement

import sys
import time
import re
import socket
from select import select

from exceptions import CommandTimeout
from django.conf import settings
import collections



def _endswith(char_list, substring):
    tail = char_list[-1 * len(substring):]
    substring = list(substring)
    return tail == substring


def _has_newline(bytelist):
    return '\r' in bytelist or '\n' in bytelist


def output_loop(*args, **kwargs):
    OutputLooper(*args, **kwargs).loop()


class OutputLooper(object):
    def __init__(self, chan, attr, stream, capture, timeout):
        self.chan = chan
        self.stream = stream
        self.capture = capture
        self.timeout = timeout
        self.read_func = getattr(chan, attr)
        self.prefix = "[HOST] %s: " % (
            "out" if attr == 'recv' else "err"
        )
        self.printing = False 
        self.linewise = True 
        self.reprompt = False
        self.read_size = 4096
        self.write_buffer = collections.deque(maxlen=len(self.prefix))

    def _flush(self, text):
        self.stream.write(text)
        self.stream.flush()
        self.write_buffer.extend(text)

    def loop(self):
        """
        Loop, reading from <chan>.<attr>(), writing to <stream> and buffering to <capture>.

        Will raise `exceptions.CommandTimeout` if network timeouts
        continue to be seen past the defined ``self.timeout`` threshold.
        (Timeouts before then are considered part of normal short-timeout fast
        network reading;)
        """
        # Internal capture-buffer-like buffer, used solely for state keeping.
        # Unlike 'capture', nothing is ever purged from this.
        _buffer = []

        # Initialize loop variables
        initial_prefix_printed = False
        seen_cr = False
        line = []

        # Allow prefix to be turned off.
        if not getattr(settings,'OUTPUT_PREFFIX',None):
            self.prefix = ""

        start = time.time()
        while True:
            # Handle actual read
            try:
                bytelist = self.read_func(self.read_size)
            except socket.timeout:
                elapsed = time.time() - start
                if self.timeout is not None and elapsed > self.timeout:
                    raise CommandTimeout
                continue
            # Empty byte == EOS
            if bytelist == '':
                # If linewise, ensure we flush any leftovers in the buffer.
                if self.linewise and line:
                    self._flush(self.prefix)
                    self._flush("".join(line))
                break
            # A None capture variable implies that we're in open_shell()
            if self.capture is None:
                # Just print directly -- no prefixes, no capturing, nada
                # And since we know we're using a pty in this mode, just go
                # straight to stdout.
                self._flush(bytelist)
            # Otherwise, we're in run/sudo and need to handle capturing and
            # prompts.
            else:
                # Print to user
                if self.printing:
                    printable_bytes = bytelist
                    # Small state machine to eat \n after \r
                    if printable_bytes[-1] == "\r":
                        seen_cr = True
                    if printable_bytes[0] == "\n" and seen_cr:
                        printable_bytes = printable_bytes[1:]
                        seen_cr = False

                    while _has_newline(printable_bytes) and printable_bytes != "":
                        # at most 1 split !
                        cr = re.search("(\r\n|\r|\n)", printable_bytes)
                        if cr is None:
                            break
                        end_of_line = printable_bytes[:cr.start(0)]
                        printable_bytes = printable_bytes[cr.end(0):]

                        if not initial_prefix_printed:
                            self._flush(self.prefix)

                        if _has_newline(end_of_line):
                            end_of_line = ''

                        if self.linewise:
                            self._flush("".join(line) + end_of_line + "\n")
                            line = []
                        else:
                            self._flush(end_of_line + "\n")
                        initial_prefix_printed = False

                    if self.linewise:
                        line += [printable_bytes]
                    else:
                        if not initial_prefix_printed:
                            self._flush(self.prefix)
                            initial_prefix_printed = True
                        self._flush(printable_bytes)

                # Now we have handled printing, handle interactivity
                read_lines = re.split(r"(\r|\n|\r\n)", bytelist)
                for fragment in read_lines:
                    # Store in capture buffer
                    self.capture += fragment
                    # Store in internal buffer
                    _buffer += fragment

        # Print trailing new line if the last thing we printed was our line
        # prefix.
        if self.prefix and "".join(self.write_buffer) == self.prefix:
            self._flush('\n')



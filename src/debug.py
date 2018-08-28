"""Code for managing the debug buffer and printing debug messages."""

from __future__ import unicode_literals

from src.weechat_wrapper import w

# HACK HACK HACK
# These used to be globals in wee_slack.py
# We should replace this whole thing with a DebugLogger class that contains
# all this stuff inside it, and create one at plugin load or something.
slack_debug = None
debug_string = None
debug_level = 0

def closed_slack_debug_buffer_cb(data, buffer):
    global slack_debug
    slack_debug = None
    return w.WEECHAT_RC_OK

def create_slack_debug_buffer():
    global slack_debug, debug_string
    if slack_debug is not None:
        w.buffer_set(slack_debug, "display", "1")
    else:
        debug_string = None
        slack_debug = w.buffer_new("slack-debug", "", "", "closed_slack_debug_buffer_cb", "")
        w.buffer_set(slack_debug, "notify", "0")

def set_debug_level(level):
    global debug_level
    debug_level = level

def dbg(message, level=0, main_buffer=False, fout=False):
    """
    send debug output to the slack-debug buffer and optionally write to a file.
    """
    # TODO: do this smarter
    # return
    if level >= debug_level:
        global debug_string
        message = "DEBUG: {}".format(message)
        if fout:
            file('/tmp/debug.log', 'a+').writelines(message + '\n')
        if main_buffer:
                # w.prnt("", "---------")
                w.prnt("", "slack: " + message)
        else:
            if slack_debug and (not debug_string or debug_string in message):
                # w.prnt(slack_debug, "---------")
                w.prnt(slack_debug, message)


"""Wrapper and mock classes for the weechat plugin handle."""

from __future__ import unicode_literals

from src.util import encode_to_utf8,decode_from_utf8

class WeechatWrapper(object):
    def __init__(self, wrapped_class):
        self.wrapped_class = wrapped_class

    # Helper method used to encode/decode method calls.
    def wrap_for_utf8(self, method):
        def hooked(*args, **kwargs):
            result = method(*encode_to_utf8(args), **encode_to_utf8(kwargs))
            # Prevent wrapped_class from becoming unwrapped
            if result == self.wrapped_class:
                return self
            return decode_from_utf8(result)
        return hooked

    # Encode and decode everything sent to/received from weechat. We use the
    # unicode type internally in wee-slack, but has to send utf8 to weechat.
    def __getattr__(self, attr):
        orig_attr = self.wrapped_class.__getattribute__(attr)
        if callable(orig_attr):
            return self.wrap_for_utf8(orig_attr)
        else:
            return decode_from_utf8(orig_attr)

    # Ensure all lines sent to weechat specifies a prefix. For lines after the
    # first, we want to disable the prefix, which is done by specifying a space.
    def prnt_date_tags(self, buffer, date, tags, message):
        message = message.replace("\n", "\n \t")
        return self.wrap_for_utf8(self.wrapped_class.prnt_date_tags)(buffer, date, tags, message)


class FakeWeechat():
    """
    Mock WeechatWrapper for use in tests.
    """
    WEECHAT_RC_ERROR = 0
    WEECHAT_RC_OK = 1
    WEECHAT_RC_OK_EAT = 2

    def __init__(self):
        pass
        #print "INITIALIZE FAKE WEECHAT"
    def prnt(*args):
        output = "("
        for arg in args:
            if arg != None:
                output += "{}, ".format(arg)
        print "w.prnt {}".format(output)
    def hdata_get(*args):
        return "0x000001"
    def hdata_pointer(*args):
        return "0x000002"
    def hdata_time(*args):
        return "1355517519"
    def hdata_string(*args):
        return "testuser"
    def buffer_new(*args):
        return "0x8a8a8a8b"
    def prefix(self, type):
        return ""
    def config_get(self, key):
     return ""
    def config_get_plugin(self, key):
        return ""
    def config_string(self, key):
     return ""
    def color(self, name):
        return ""
    def __getattr__(self, name):
        def method(*args):
            pass
            #print "called {}".format(name)
            #if args:
            #    print "\twith args: {}".format(args)
        return method


# hack to make tests possible.. better way?
try:
    import weechat
    w = WeechatWrapper(weechat)
except:
    w = FakeWeechat()

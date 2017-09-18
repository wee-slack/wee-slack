import json
import pytest
import sys

sys.path.append(".")

#New stuff
from wee_slack import EventRouter
from wee_slack import SlackRequest
import wee_slack

class fakewebsocket(object):
    def __init__(self):
        self.returndata = []
        pass
    def add(self, data):
        self.returndata.append(data)
    def recv(self):
        return json.dumps(self.returndata.pop(0))
    def send(self, data):
        print "websocket received: {}".format(data)
        return

@pytest.fixture
def mock_websocket():
    return fakewebsocket()

@pytest.fixture
def realish_eventrouter(mock_weechat):
    e = EventRouter()
    context = e.store_context(SlackRequest('xoxoxoxox', "rtm.start", {"meh": "blah"}))
    rtmstartdata = open('_pytest/data/http/rtm.start.json', 'r').read()
    e.receive_httprequest_callback(context, 1, 0, rtmstartdata, 4)
    while len(e.queue):
        e.handle_next()
    #e.sc is just shortcuts to these items
    e.sc = {}
    e.sc["team_id"] = e.teams.keys()[0]
    e.sc["team"] = e.teams[e.sc["team_id"]]
    e.sc["user"] = e.teams[e.sc["team_id"]].users[e.teams[e.sc["team_id"]].users.keys()[0]]
    socket = mock_websocket
    e.teams[e.sc["team_id"]].ws = socket

    return e


class FakeWeechat():
    """
    this is the thing that acts as "w." everywhere..
    basically mock out all of the weechat calls here i guess
    """
    WEECHAT_RC_OK = True

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
    def config_get_plugin(self, key):
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

@pytest.fixture
def mock_weechat():
    wee_slack.w = FakeWeechat()
    wee_slack.config = wee_slack.PluginConfig()
    wee_slack.debug_string = None
    wee_slack.slack_debug = "debug_buffer_ptr"
    wee_slack.STOP_TALKING_TO_SLACK = False
    wee_slack.proc = {}
    wee_slack.weechat_version = 0x10500000
    pass



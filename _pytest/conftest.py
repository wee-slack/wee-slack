import json
import pytest
import sys

sys.path.append(".")

#New stuff
from wee_slack import EventRouter
from wee_slack import SlackRequest
from src import config
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


@pytest.fixture
def mock_weechat():
    import wee_slack
    wee_slack.config = config.PluginConfig()
    wee_slack.STOP_TALKING_TO_SLACK = False
    wee_slack.proc = {}
    wee_slack.weechat_version = 0x10500000
    import src.debug
    src.debug.slack_debug = "debug_buffer_ptr"

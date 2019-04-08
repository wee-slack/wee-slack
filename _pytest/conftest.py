from __future__ import print_function, unicode_literals

import json
import pytest
import random
import string
import sys

sys.path.append(".")

import wee_slack
from wee_slack import EventRouter, SlackRequest

class fakewebsocket(object):
    def __init__(self):
        self.returndata = []
        self.sentdata = []
    def add(self, data):
        self.returndata.append(data)
    def recv(self):
        return json.dumps(self.returndata.pop(0))
    def send(self, data):
        self.sentdata.append(data)

@pytest.fixture
def mock_websocket():
    return fakewebsocket()

@pytest.fixture
def realish_eventrouter(mock_websocket, mock_weechat):
    e = EventRouter()
    context = e.store_context(SlackRequest('xoxs-token', 'rtm.start', {}))
    with open('_pytest/data/http/rtm.start.json') as rtmstartfile:
        if sys.version_info.major == 2:
            rtmstartdata = rtmstartfile.read().decode('utf-8')
        else:
            rtmstartdata = rtmstartfile.read()
        e.receive_httprequest_callback(context, '', 0, rtmstartdata, '')
    while len(e.queue):
        e.handle_next()
    for team in e.teams.values():
        team.ws = mock_websocket
    return e

@pytest.fixture
def team(realish_eventrouter):
    return next(iter(realish_eventrouter.teams.values()))

@pytest.fixture
def channel_general(team):
    return team.channels[team.get_channel_map()['general']]

@pytest.fixture
def user_alice(team):
    return team.users[team.get_username_map()['alice']]

class FakeWeechat():
    """
    this is the thing that acts as "w." everywhere..
    basically mock out all of the weechat calls here i guess
    """
    WEECHAT_RC_ERROR = 0
    WEECHAT_RC_OK = 1
    WEECHAT_RC_OK_EAT = 2
    def __init__(self):
        self.config = {}
    def prnt(*args):
        output = "("
        for arg in args:
            if arg != None:
                output += "{}, ".format(arg)
        print("w.prnt {}".format(output))
    def hdata_get(*args):
        return "0x000001"
    def hdata_pointer(*args):
        return "0x000002"
    def hdata_time(*args):
        return "1355517519"
    def hdata_string(*args):
        return "testuser"
    def buffer_new(*args):
        return "0x" + "".join(random.choice(string.digits) for _ in range(8))
    def prefix(self, type):
        return ""
    def config_get_plugin(self, key):
        return self.config.get(key, "")
    def config_get(self, key):
        return ""
    def config_set_plugin(self, key, value):
        self.config[key] = value
    def config_string(self, key):
        return ""
    def color(self, name):
        return ""
    def __getattr__(self, name):
        def method(*args):
            pass
        return method

@pytest.fixture
def mock_weechat():
    wee_slack.w = FakeWeechat()
    wee_slack.config = wee_slack.PluginConfig()
    wee_slack.hdata = wee_slack.Hdata(wee_slack.w)
    wee_slack.debug_string = None
    wee_slack.slack_debug = "debug_buffer_ptr"
    wee_slack.STOP_TALKING_TO_SLACK = False
    wee_slack.proc = {}
    wee_slack.weechat_version = 0x10500000

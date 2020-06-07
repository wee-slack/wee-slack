from __future__ import print_function, unicode_literals

import json
import pytest
import random
import ssl
import string
import sys

from websocket import ABNF

sys.path.append(".")

import wee_slack
from wee_slack import EventRouter, SlackRequest, initiate_connection

class fakewebsocket(object):
    def __init__(self):
        self.returndata = []
        self.sentdata = []
    def add(self, data):
        self.returndata.append(json.dumps(data).encode('utf-8'))
    def recv(self):
        return self.recv_data()[1].decode('utf-8')
    def recv_data(self, control_frame=False):
        if self.returndata:
            return ABNF.OPCODE_TEXT, self.returndata.pop(0)
        else:
            raise ssl.SSLWantReadError()
    def send(self, data):
        self.sentdata.append(data)

@pytest.fixture
def mock_websocket():
    return fakewebsocket()

@pytest.fixture
def realish_eventrouter(mock_websocket, mock_weechat):
    e = EventRouter()
    wee_slack.EVENTROUTER = e
    context = e.store_context(initiate_connection('xoxs-token'))
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
    return team.channels[team.get_channel_map()['#general']]

@pytest.fixture
def channel_private(team):
    return team.channels[team.get_channel_map()['&some-private-channel']]

@pytest.fixture
def channel_dm(team):
    return team.channels[team.get_channel_map()['alice']]

@pytest.fixture
def channel_mpdm(team):
    return team.channels[team.get_channel_map()['CharlesTestuser,alice']]

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
    def hdata_integer(*args):
        return 1
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
    def config_integer(self, key):
        return 1000
    def config_set_plugin(self, key, value):
        self.config[key] = value
    def config_string(self, key):
        return ""
    def color(self, name):
        return "<[color {}]>".format(name)
    def info_get(self, info_name, arguments):
        if info_name == "color_rgb2term":
            return arguments
        else:
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

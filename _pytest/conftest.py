import pytest
import sys

sys.path.append(".")
#sys.path.append(str(pytest.config.rootdir))

from wee_slack import SlackServer
from wee_slack import Channel
from wee_slack import User
from wee_slack import SearchList
import wee_slack

class FakeWeechat():
    """
    this is the thing that acts as "w." everywhere..
    basically mock out all of the weechat calls here i guess
    """
    WEECHAT_RC_OK = True

    def __init__(self):
        print "INITIALIZE FAKE WEECHAT"
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

    def __getattr__(self, name):
        def method(*args):
            print "called {}".format(name)
            if args:
                print "\twith args: {}".format(args)
        return method

@pytest.fixture
def fake_weechat():
    wee_slack.w = FakeWeechat()
    pass


@pytest.fixture
def slack_debug():
    wee_slack.slack_debug = "debug_buffer_ptr"

@pytest.fixture
def server(fake_weechat, monkeypatch):
#def server(monkeypatch, mychannels, myusers):
    def mock_connect_to_slack(*args):
        return True
    monkeypatch.setattr(SlackServer, 'connect_to_slack', mock_connect_to_slack)
    myserver = SlackServer('xoxo-12345')
    myserver.identifier = 'test.slack.com'
    myserver.nick = 'myusername'
    return myserver

@pytest.fixture
def myservers(server):
    servers = SearchList()
    servers.append(server)
    return servers



@pytest.fixture
def channel(monkeypatch, server):
    def mock_buffer_prnt(*args):
        print "called buffer_prnt\n\twith args: {}".format(args)
        return
    def mock_do_nothing(*args):
        print args
        return True
    monkeypatch.setattr(Channel, 'create_buffer', mock_do_nothing)
    monkeypatch.setattr(Channel, 'attach_buffer', mock_do_nothing)
    monkeypatch.setattr(Channel, 'set_topic', mock_do_nothing)
    monkeypatch.setattr(Channel, 'set_topic', mock_do_nothing)
    monkeypatch.setattr(Channel, 'buffer_prnt', mock_buffer_prnt)
    mychannel = Channel(server, '#testchan', 'C2147483705', True, last_read=0, prepend_name="", members=[], topic="")
    return mychannel

@pytest.fixture
def mychannels(channel):
    channels = SearchList()
    channels.append(channel)
    return channels

@pytest.fixture
def user(monkeypatch, server):
    wee_slack.domain = None
    wee_slack.colorize_nicks = True
    pass
    myuser = User(server, "testuser", 'U2147483697', presence="away")
    myuser.color = ''
    return myuser

@pytest.fixture
def myusers(monkeypatch, user):
    users = SearchList()
    users.append(user)
    return users


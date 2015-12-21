
import wee_slack
import pytest
import json
from collections import defaultdict


def test_process_message(slack_debug, monkeypatch, myservers, mychannels, myusers):
    called = defaultdict(int)
    wee_slack.servers = myservers
    wee_slack.channels = mychannels
    wee_slack.users = myusers
    wee_slack.message_cache = {}
    wee_slack.servers[0].users = myusers
    wee_slack.unfurl_ignore_alt_text = False

    def mock_buffer_prnt(*args):
        called['buffer_prnt'] += 1
    monkeypatch.setattr(wee_slack.Channel, 'buffer_prnt', mock_buffer_prnt)

#    def mock_buffer_prnt_changed(*args):
#        called['buffer_prnt_changed'] += 1
#        print args
#    monkeypatch.setattr(wee_slack.Channel, 'buffer_prnt_changed', mock_buffer_prnt_changed)


    messages = []
    messages.append( json.loads(open('_pytest/data/message-normal.json', 'r').read()) )
    messages.append( json.loads(open('_pytest/data/message-normal2.json', 'r').read()) )
    messages.append( json.loads(open('_pytest/data/message-changed.json', 'r').read()) )
    messages.append( json.loads(open('_pytest/data/message-deleted.json', 'r').read()) )
    for m in messages:
        wee_slack.process_message(m)
    print "---"
    print called
    print "---"
#    assert called['buffer_prnt'] == 2
#    assert called['buffer_prnt_changed'] == 1

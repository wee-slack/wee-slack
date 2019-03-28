from __future__ import print_function, unicode_literals

from wee_slack import SlackRequest, EventRouter

def test_SlackRequest():
    s = SlackRequest('xoxoxoxox', "blah.get", {"meh": "blah"})
    print(s)

    e = EventRouter()
    e.receive(s)
    e.handle_next()
    #assert False


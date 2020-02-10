from __future__ import print_function, unicode_literals

import pytest
from wee_slack import EventRouter, SlackRequest


def test_EventRouter(mock_weechat):
    # Sending valid object adds to the queue.
    e = EventRouter()
    e.receive({})
    assert len(e.queue) == 1

    # Handling an event removes from the queue.
    e = EventRouter()
    # Create a function to test we are called
    e.proc['testfunc'] = lambda json, eventrouter, team, channel, metadata: json
    e.receive({"type": "testfunc"})
    e.handle_next()
    assert len(e.queue) == 0

    # Handling a local event removes from the queue.
    e = EventRouter()
    # Create a function to test we are called
    e.proc['local_testfunc'] = lambda json, eventrouter, team, channel, metadata: json
    e.receive({"type": "local_testfunc"})
    e.handle_next()
    assert len(e.queue) == 0

    # Handling an event without an associated processor
    # shouldn't raise an exception.
    e = EventRouter()
    # Create a function to test we are called
    e.receive({"type": "testfunc"})
    e.handle_next()

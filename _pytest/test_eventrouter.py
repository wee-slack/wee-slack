import pytest
from wee_slack import EventRouter, SlackRequest

def test_EventRouter(mock_weechat):
    # Sending valid json adds to the queue.
    e = EventRouter()
    e.receive_json('{}')
    assert len(e.queue) == 1

    # Handling an event removes from the queue.
    e = EventRouter()
    # Create a function to test we are called
    e.proc['testfunc'] = lambda x, y: x
    e.receive_json('{"type": "testfunc"}')
    e.handle_next()
    assert len(e.queue) == 0

    # Handling a local event removes from the queue.
    e = EventRouter()
    # Create a function to test we are called
    e.proc['local_testfunc'] = lambda x, y: x
    e.receive_json('{"type": "local_testfunc"}')
    e.handle_next()
    assert len(e.queue) == 0

    # Handling an event without an associated processor
    # shouldn't raise an exception.
    e = EventRouter()
    # Create a function to test we are called
    e.receive_json('{"type": "testfunc"}')
    e.handle_next()

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

def test_EventRouterReceivedata(mock_weechat):

    e = EventRouter()
    context = e.store_context(SlackRequest('xoxoxoxox', "rtm.startold", {"meh": "blah"}))
    print context
    e.receive_httprequest_callback(context, 1, -1, ' {"JSON": "MEH", ', 4)
    #print len(e.reply_buffer)
    context = e.store_context(SlackRequest('xoxoxoxox', "rtm.startold", {"meh": "blah"}))
    print context
    e.receive_httprequest_callback(context, 1, -1, ' "JSON2": "MEH", ', 4)
    #print len(e.reply_buffer)
    context = e.store_context(SlackRequest('xoxoxoxox', "rtm.startold", {"meh": "blah"}))
    print context
    e.receive_httprequest_callback(context, 1, 0, ' "JSON3": "MEH"}', 4)
    #print len(e.reply_buffer)
    try:
        e.handle_next()
        e.handle_next()
        e.handle_next()
        e.handle_next()
    except:
        pass

    print e.context
    #assert False

    context = e.store_context(SlackRequest('xoxoxoxox', "rtm.start", {"meh": "blah"}))
    rtmstartdata = open('_pytest/data/http/rtm.start.json', 'r').read()
    e.receive_httprequest_callback(context, 1, -1, rtmstartdata[:5000], 4)
    e.receive_httprequest_callback(context, 1, 0, rtmstartdata[5000:], 4)
    e.handle_next()

    #print len(e.reply_buffer)

    #print e.teams

    for t in e.teams:
        #print vars(e.teams[t])
        for c in e.teams[t].channels:
            pass
            #print c
        for u in e.teams[t].users:
            pass
            #print vars(u)


#    e = EventRouter()
#    # Create a function to test we are called
#    e.receive_json('{"type": "message"}')
#    e.handle_next()
#    assert False

    #assert False

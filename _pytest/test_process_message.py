import json

from wee_slack import render

def test_process_message(realish_eventrouter, mock_websocket):

    e = realish_eventrouter

    t = e.teams.keys()[0]
    u = e.teams[t].users.keys()[0]

    user = e.teams[t].users[u]
    #print user

    socket = mock_websocket
    e.teams[t].ws = socket

    messages = []
    messages.append(json.loads(open('_pytest/data/websocket/1485975421.33-message.json', 'r').read()))

    # test message and then change
    messages.append(json.loads(open('_pytest/data/websocket/1485976157.18-message.json', 'r').read()))
    messages.append(json.loads(open('_pytest/data/websocket/1485976151.6-message.json', 'r').read()))

    # test message then deletion
    messages.append(json.loads(open('_pytest/data/websocket/1485975698.45-message.json', 'r').read()))
    messages.append(json.loads(open('_pytest/data/websocket/1485975723.85-message.json', 'r').read()))

    for m in messages:
        m["user"] = user.id
        socket.add(m)

    e.receive_ws_callback(t)
    e.handle_next()

    e.receive_ws_callback(t)
    e.handle_next()

    e.receive_ws_callback(t)
    e.handle_next()

    e.receive_ws_callback(t)
    e.handle_next()


    #assert e.teams[t].channels['C407ABS94'].messages.keys()[0] == '1485976151.00016'
    #assert False


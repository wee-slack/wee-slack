
def test_send_message(realish_eventrouter, mock_websocket):
    e = realish_eventrouter

    t = e.teams.keys()[0]
    #u = e.teams[t].users.keys()[0]

    #user = e.teams[t].users[u]
    #print user

    socket = mock_websocket
    e.teams[t].ws = socket

    c = e.teams[t].channels.keys()[0]

    channel = e.teams[t].channels[c]
    channel.send_message('asdf')

    print c

    #assert False

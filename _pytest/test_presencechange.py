
def test_PresenceChange(realish_eventrouter, mock_websocket):

    e = realish_eventrouter

    t = e.teams.keys()[0]
    u = e.teams[t].users.keys()[0]

    user = e.teams[t].users[u]

    socket = mock_websocket
    e.teams[t].ws = socket

    socket.add({
        "type": "presence_change",
        "user": user.identifier,
        "presence": "active",
    })
    socket.add({
        "type": "presence_change",
        "user": user.identifier,
        "presence": "away",
    })

    e.receive_ws_callback(t)
    e.handle_next()
    assert e.teams[t].users[u].presence == "active"

    e.receive_ws_callback(t)
    e.handle_next()
    assert e.teams[t].users[u].presence == "away"

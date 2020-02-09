from __future__ import print_function, unicode_literals


def test_PresenceChange(realish_eventrouter, team, user_alice):
    team.ws.add({
        "type": "presence_change",
        "user": user_alice.identifier,
        "presence": "active",
    })
    team.ws.add({
        "type": "presence_change",
        "user": user_alice.identifier,
        "presence": "away",
    })
    realish_eventrouter.receive_ws_callback(team.team_hash, None)

    realish_eventrouter.handle_next()
    assert user_alice.presence == "active"

    realish_eventrouter.handle_next()
    assert user_alice.presence == "away"

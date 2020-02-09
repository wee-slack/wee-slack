from __future__ import print_function, unicode_literals

import json


def test_process_team_join(realish_eventrouter, team):
    # delete charles so we can add him
    del team.users['U4096CBHC']

    assert len(team.users) == 3

    datafile = '_pytest/data/websocket/1485975606.59-team_join.json'
    data = json.loads(open(datafile, 'r').read())
    team.ws.add(data)
    realish_eventrouter.receive_ws_callback(team.team_hash, None)
    realish_eventrouter.handle_next()

    assert len(team.users) == 4

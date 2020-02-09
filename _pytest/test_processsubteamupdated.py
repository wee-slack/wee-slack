from __future__ import print_function, unicode_literals

import json


def test_process_subteam_self_updated(realish_eventrouter, team):
    assert len(team.subteams) == 1

    datafile = '_pytest/data/websocket/1483975206.59-subteam_updated.json'
    data = json.loads(open(datafile, 'r').read())
    team.ws.add(data)
    realish_eventrouter.receive_ws_callback(team.team_hash, None)
    realish_eventrouter.handle_next()
    subteam = team.subteams['TGX0ALBK3']

    assert '@{}'.format(data['subteam']['handle']) == subteam.handle
    assert data['subteam']['description'] == subteam.description
    assert data['subteam']['name'] == subteam.name

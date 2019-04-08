import glob
from mock import patch, call
from wee_slack import SlackTeam, SlackSubteam
import json

def test_process_subteam_self_updated(mock_websocket, realish_eventrouter):

    eventrouter = realish_eventrouter

    t = eventrouter.teams.keys()[0]

    assert len(eventrouter.teams[t].subteams) == 1

    socket = mock_websocket
    eventrouter.teams[t].ws = socket
    datafiles = glob.glob("_pytest/data/websocket/1483975206.59-subteam_updated.json")

    for fname in datafiles:
        data = json.loads(open(fname, 'r').read())
        socket.add(data)
        eventrouter.receive_ws_callback(t)
        eventrouter.handle_next()
    team = eventrouter.teams[t]
    subteam = team.subteams.values()[0]

    assert data['subteam']['handle'] == subteam.handle
    assert data['subteam']['description'] == subteam.description
    assert data['subteam']['name'] == subteam.name


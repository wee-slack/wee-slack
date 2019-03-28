import glob
from mock import patch
from wee_slack import SlackTeam
import json

def test_process_subteam_self_added(mock_websocket, realish_eventrouter):

    eventrouter = realish_eventrouter

    t = eventrouter.teams.keys()[0]

    assert len(eventrouter.teams[t].subteams) == 1

    socket = mock_websocket
    eventrouter.teams[t].ws = socket
    datafiles = glob.glob("_pytest/data/websocket/1483975206.59-subteam_self_removed.json")

    with patch('wee_slack.SlackTeam.buffer_prnt') as fake_buffer_prnt:
        for fname in datafiles:
            data = json.loads(open(fname, 'r').read())
            socket.add(data)
            eventrouter.receive_ws_callback(t)
            eventrouter.handle_next()
        team = eventrouter.teams[t]
        team.buffer_prnt = fake_buffer_prnt

        subteam = team.subteams.values()[0]
        subteam_name = subteam.name
        subteam_handle = subteam.handle
        template = 'You have been removed from usergroup {subteam} ({handle}) in team {team}'
        message = template.format(subteam=subteam_name, handle=subteam_handle , team=team.preferred_name)
        fake_buffer_prnt.assert_called_with(message, message=True)

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

    with patch('wee_slack.SlackTeam.buffer_prnt') as fake_buffer_prnt:
        for fname in datafiles:
            data = json.loads(open(fname, 'r').read())
            socket.add(data)
            eventrouter.receive_ws_callback(t)
            eventrouter.handle_next()
        team = eventrouter.teams[t]
        team.buffer_prnt = fake_buffer_prnt

        old_rtm = json.loads(open('_pytest/data/http/rtm.start.json', 'r').read())
        old_subteam_json = old_rtm['subteams']['all'][0]
        subteam = SlackSubteam(team.identifier, **old_subteam_json)

        subteam_name = subteam.name
        subteam_handle = subteam.handle
        new_subteam_name = data['subteam']['name']
        new_subteam_description = data['subteam']['description']
        new_subteam_handle = data['subteam']['handle']


        template_for_name_change = '{current_name} has updated its name to {new_name} in team {team}'
        message_for_name_change = template_for_name_change.format(current_name=subteam_name, new_name=new_subteam_name, team=team.preferred_name)

        template_for_description_change = '{name} has updated its description to \"{description}\" in team {team}'
        message_for_description_change = template_for_description_change.format(name=subteam_name, description=new_subteam_description, team=team.preferred_name)

        template_for_handle_change = '{name} has updated its handle to @{handle} in team {team}'
        message_for_handle_change = template_for_handle_change.format(name=subteam_name, handle=new_subteam_handle , team=team.preferred_name)
        calls = [call(message_for_name_change, message=True), call(message_for_description_change, message=True), call(message_for_handle_change, message=True)]

        fake_buffer_prnt.assert_has_calls(calls)

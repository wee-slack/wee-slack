from __future__ import print_function, unicode_literals

import json

from wee_slack import SlackTS, command_reply

parent_ts = SlackTS('1485975824.000004')
child_ts = SlackTS('1485975835.000005')

def test_replying_to_child_should_use_parent_ts(realish_eventrouter, team, channel_general):
    datafiles = [
            '_pytest/data/websocket/1485975824.48-message.json',
            '_pytest/data/websocket/1485975836.23-message.json'
    ]
    for datafile in datafiles:
        data = json.loads(open(datafile).read())
        team.ws.add(data)
        realish_eventrouter.receive_ws_callback(team.team_hash, None)
        realish_eventrouter.handle_next()

    child_hash = channel_general.hashed_messages[child_ts]
    command_reply(None, channel_general.channel_buffer, '${} test'.format(child_hash))

    sent = json.loads(team.ws.sentdata[0])
    assert sent['thread_ts'] == parent_ts

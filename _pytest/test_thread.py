from __future__ import print_function, unicode_literals

import json

from wee_slack import SlackTS


thread_ts = SlackTS('1485975824.000004')


def test_message_has_thread_suffix(realish_eventrouter, team, channel_general):
    datafile = '_pytest/data/websocket/1485975824.48-message.json'
    data = json.loads(open(datafile).read())
    team.ws.add(data)
    realish_eventrouter.receive_ws_callback(team.team_hash, None)
    realish_eventrouter.handle_next()

    message_text = channel_general.messages[thread_ts].message_json['_rendered_text']
    assert message_text == 'generally, yep!'

    datafile = '_pytest/data/websocket/1485975836.23-message.json'
    data = json.loads(open(datafile).read())
    team.ws.add(data)
    realish_eventrouter.receive_ws_callback(team.team_hash, None)
    realish_eventrouter.handle_next()

    message_text = channel_general.messages[thread_ts].message_json['_rendered_text']
    assert message_text == 'generally, yep! <[color lightcyan]>[ Thread: 309 Replies: 1 ]<[color reset]>'

    datafile = '_pytest/data/websocket/1485975842.1-message.json'
    data = json.loads(open(datafile).read())
    team.ws.add(data)
    realish_eventrouter.receive_ws_callback(team.team_hash, None)
    realish_eventrouter.handle_next()

    message_text = channel_general.messages[thread_ts].message_json['_rendered_text']
    assert message_text == 'generally, yep! <[color lightcyan]>[ Thread: 309 Replies: 2 ]<[color reset]>'

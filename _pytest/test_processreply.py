from __future__ import print_function, unicode_literals

from wee_slack import SlackTS


def test_process_reply(realish_eventrouter, team, channel_general):
    message_ts = SlackTS('12341234.123456')
    message_text = 'reply test'
    channel_general.send_message(message_text)
    team.ws.add({'ok': True, 'reply_to': 1, '_team': team.team_hash, 'ts': str(message_ts)})
    realish_eventrouter.receive_ws_callback(team.team_hash, None)
    realish_eventrouter.handle_next()

    assert message_ts in channel_general.messages
    message_json = channel_general.messages[message_ts].message_json
    assert message_json['ts'] == message_ts
    assert message_json['text'] == message_text

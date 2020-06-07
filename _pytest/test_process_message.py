from __future__ import print_function, unicode_literals

import json

from wee_slack import SlackTS


def test_process_message(realish_eventrouter, team, user_alice):
    messages = []
    messages.append(json.loads(open('_pytest/data/websocket/1485975421.33-message.json', 'r').read()))

    # test message and then change
    messages.append(json.loads(open('_pytest/data/websocket/1485976151.6-message.json', 'r').read()))
    messages.append(json.loads(open('_pytest/data/websocket/1485976157.18-message.json', 'r').read()))

    # test message then deletion
    messages.append(json.loads(open('_pytest/data/websocket/1485975698.45-message.json', 'r').read()))
    messages.append(json.loads(open('_pytest/data/websocket/1485975723.85-message.json', 'r').read()))

    for m in messages:
        m["user"] = user_alice.id
        team.ws.add(m)

    realish_eventrouter.receive_ws_callback(team.team_hash, None)
    realish_eventrouter.handle_next()
    realish_eventrouter.handle_next()
    realish_eventrouter.handle_next()
    realish_eventrouter.handle_next()
    realish_eventrouter.handle_next()

    assert sum([len(channel.messages) for channel in team.channels.values()]) == 3

    unchanged_message_channel = team.channels['D3ZEQULHZ']
    unchanged_message_ts = SlackTS('1485975421.000002')
    assert list(unchanged_message_channel.messages.keys()) == [unchanged_message_ts]
    assert unchanged_message_channel.messages[unchanged_message_ts].message_json['text'] == 'hi bob'
    assert 'edited' not in unchanged_message_channel.messages[unchanged_message_ts].message_json

    changed_message_channel = team.channels['C407ABS94']
    changed_message_ts = SlackTS('1485976151.000016')
    assert list(changed_message_channel.messages.keys()) == [changed_message_ts]
    assert changed_message_channel.messages[changed_message_ts].message_json['text'] == 'referencing a <#C407ABS94|general>'
    assert 'edited' in changed_message_channel.messages[changed_message_ts].message_json

    deleted_message_channel = team.channels['G3ZGMF4RZ']
    deleted_message_ts = SlackTS('1485975698.000002')
    assert list(deleted_message_channel.messages.keys()) == [deleted_message_ts]
    deleted_str = '<[color red]>(deleted)<[color reset]>'
    assert deleted_message_channel.messages[deleted_message_ts].message_json['text'] == deleted_str

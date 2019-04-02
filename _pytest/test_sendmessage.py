from __future__ import print_function, unicode_literals

import json


def test_send_message(realish_eventrouter, team, channel_general):
    message_text = 'send message test'
    channel_general.send_message(message_text)

    sent = json.loads(team.ws.sentdata[0])

    assert sent == {
        'text': message_text,
        'type': 'message',
        'user': team.myidentifier,
        'channel': channel_general.id,
        'id': 1,
    }

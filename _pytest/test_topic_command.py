from __future__ import print_function, unicode_literals

import wee_slack
from wee_slack import parse_topic_command, topic_command_cb
from mock import patch


def test_parse_topic_without_arguments():
    channel_name, topic = parse_topic_command('/topic')

    assert channel_name is None
    assert topic is None


def test_parse_topic_with_text():
    channel_name, topic = parse_topic_command('/topic some topic text')

    assert channel_name is None
    assert topic == 'some topic text'


def test_parse_topic_with_text_with_newline():
    channel_name, topic = parse_topic_command('/topic some topic text\nsecond line')

    assert channel_name is None
    assert topic == 'some topic text\nsecond line'


def test_parse_topic_with_delete():
    channel_name, topic = parse_topic_command('/topic -delete')

    assert channel_name is None
    assert topic == ''


def test_parse_topic_with_channel():
    channel_name, topic = parse_topic_command('/topic #general')

    assert channel_name == '#general'
    assert topic is None


def test_parse_topic_with_channel_and_text():
    channel_name, topic = parse_topic_command(
        '/topic #general some topic text')

    assert channel_name == '#general'
    assert topic == 'some topic text'


def test_parse_topic_with_channel_and_delete():
    channel_name, topic = parse_topic_command('/topic #general -delete')

    assert channel_name == '#general'
    assert topic == ''


def test_call_topic_without_arguments(realish_eventrouter, channel_general):
    current_buffer = channel_general.channel_buffer
    wee_slack.EVENTROUTER = realish_eventrouter

    command = '/topic'

    with patch('wee_slack.w.prnt') as fake_prnt:
        result = topic_command_cb(None, current_buffer, command)
        fake_prnt.assert_called_with(
            channel_general.channel_buffer,
            'Topic for {} is "{}"'.format(channel_general.name, channel_general.topic['value']),
        )
        assert result == wee_slack.w.WEECHAT_RC_OK_EAT


def test_call_topic_with_unknown_channel(realish_eventrouter, team, channel_general):
    current_buffer = channel_general.channel_buffer
    wee_slack.EVENTROUTER = realish_eventrouter

    command = '/topic #nonexisting'

    with patch('wee_slack.w.prnt') as fake_prnt:
        result = topic_command_cb(None, current_buffer, command)
        fake_prnt.assert_called_with(
            team.channel_buffer,
            "#nonexisting: No such channel",
        )
        assert result == wee_slack.w.WEECHAT_RC_OK_EAT


def test_call_topic_with_channel_and_string(realish_eventrouter, channel_general):
    current_buffer = channel_general.channel_buffer
    wee_slack.EVENTROUTER = realish_eventrouter

    command = '/topic #general new topic'

    result = topic_command_cb(None, current_buffer, command)
    request = realish_eventrouter.queue[-1]
    assert request.request == 'conversations.setTopic'
    assert request.post_data == {
        'channel': 'C407ABS94', 'token': 'xoxs-token', 'topic': 'new topic'}
    assert result == wee_slack.w.WEECHAT_RC_OK_EAT

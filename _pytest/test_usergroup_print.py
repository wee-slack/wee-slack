import wee_slack
from wee_slack import usergroup_print_cb
from mock import patch


def test_format_usergroup(realish_eventrouter):
    team = realish_eventrouter.teams.values()[-1]
    channel = team.channels.values()[-1]
    current_buffer = channel.channel_buffer
    wee_slack.EVENTROUTER = realish_eventrouter
    message = 'Generic User !subteam^DFSN3G (test) This is a test message'
    new_message = 'Generic User @test This is a test message'

    result = usergroup_print_cb(None, None, '', message)

    assert result == new_message


def test_maintain_regular_message(realish_eventrouter):
    team = realish_eventrouter.teams.values()[-1]
    channel = team.channels.values()[-1]
    current_buffer = channel.channel_buffer
    wee_slack.EVENTROUTER = realish_eventrouter
    message = 'Just a regular message'

    result = usergroup_print_cb(None, None, '', message)
    assert result == message


def test_maintain_user_highlight_message(realish_eventrouter):
    team = realish_eventrouter.teams.values()[-1]
    channel = team.channels.values()[-1]
    current_buffer = channel.channel_buffer
    wee_slack.EVENTROUTER = realish_eventrouter
    message = '@user Hey you'

    result = usergroup_print_cb(None, None, '', message)
    assert result == message 

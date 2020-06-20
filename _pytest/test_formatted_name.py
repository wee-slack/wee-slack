from __future__ import print_function, unicode_literals

import pytest
import wee_slack


@pytest.mark.parametrize('case', (
    {
        "type": "channel",
        "style": "default",
        "typing": False,
        "present": False,
        "name": "#general"
    },
    {
        "type": "channel",
        "style": "default",
        "typing": True,
        "present": True,
        "name": "#general"
    },
    {
        "type": "channel",
        "style": "long_default",
        "typing": False,
        "present": False,
        "name": "slack.weeslacktest.#general"
    },
    {
        "type": "channel",
        "style": "long_default",
        "typing": True,
        "present": True,
        "name": "slack.weeslacktest.#general"
    },
    {
        "type": "channel",
        "style": "sidebar",
        "typing": False,
        "present": False,
        "name": "#general"
    },
    {
        "type": "channel",
        "style": "sidebar",
        "typing": True,
        "present": True,
        "name": ">general"
    },
    {
        "type": "private",
        "style": "default",
        "typing": False,
        "present": False,
        "name": "&some-private-channel"
    },
    {
        "type": "private",
        "style": "default",
        "typing": True,
        "present": True,
        "name": "&some-private-channel"
    },
    {
        "type": "private",
        "style": "long_default",
        "typing": False,
        "present": False,
        "name": "slack.weeslacktest.&some-private-channel"
    },
    {
        "type": "private",
        "style": "long_default",
        "typing": True,
        "present": True,
        "name": "slack.weeslacktest.&some-private-channel"
    },
    {
        "type": "private",
        "style": "sidebar",
        "typing": False,
        "present": False,
        "name": "&some-private-channel"
    },
    {
        "type": "private",
        "style": "sidebar",
        "typing": True,
        "present": True,
        "name": ">some-private-channel"
    },
    {
        "type": "dm",
        "style": "default",
        "typing": False,
        "present": False,
        "name": "alice"
    },
    {
        "type": "dm",
        "style": "default",
        "typing": True,
        "present": True,
        "name": "alice"
    },
    {
        "type": "dm",
        "style": "long_default",
        "typing": False,
        "present": False,
        "name": "slack.weeslacktest.alice"
    },
    {
        "type": "dm",
        "style": "long_default",
        "typing": True,
        "present": True,
        "name": "slack.weeslacktest.alice"
    },
    {
        "type": "dm",
        "style": "sidebar",
        "typing": False,
        "present": False,
        "name": " alice"
    },
    {
        "type": "dm",
        "style": "sidebar",
        "typing": False,
        "present": True,
        "name": "+alice"
    },
    {
        "type": "dm",
        "style": "sidebar",
        "typing": True,
        "present": False,
        "name": ">alice"
    },
    {
        "type": "dm",
        "style": "sidebar",
        "typing": True,
        "present": True,
        "name": ">alice"
    },
    {
        "type": "mpdm",
        "style": "default",
        "typing": False,
        "present": False,
        "name": "CharlesTestuser,alice"
    },
    {
        "type": "mpdm",
        "style": "default",
        "typing": True,
        "present": True,
        "name": "CharlesTestuser,alice"
    },
    {
        "type": "mpdm",
        "style": "long_default",
        "typing": False,
        "present": False,
        "name": "slack.weeslacktest.CharlesTestuser,alice"
    },
    {
        "type": "mpdm",
        "style": "long_default",
        "typing": True,
        "present": True,
        "name": "slack.weeslacktest.CharlesTestuser,alice"
    },
    {
        "type": "mpdm",
        "style": "sidebar",
        "typing": False,
        "present": False,
        "name": "@CharlesTestuser,alice"
    },
    {
        "type": "mpdm",
        "style": "sidebar",
        "typing": True,
        "present": True,
        "name": ">CharlesTestuser,alice"
    },
))
def test_formatted_name(case, channel_general, channel_private, channel_dm, channel_mpdm):
    wee_slack.config.channel_name_typing_indicator = True
    wee_slack.config.show_buflist_presence = True
    channels = {
            "channel": channel_general,
            "private": channel_private,
            "dm": channel_dm,
            "mpdm": channel_mpdm,
    }
    name = channels[case["type"]].formatted_name(case["style"], case["typing"], case["present"])
    assert name == case["name"]

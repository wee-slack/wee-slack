import pytest

import wee_slack


@pytest.mark.parametrize(
    "case",
    [
        {
            "input_message": {
                "blocks": [
                    {
                        "type": "rich_text",
                        "block_id": "5Cg6",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [
                                    {
                                        "type": "emoji",
                                        "name": "smile",
                                        "unicode": "1f604",
                                    }
                                ],
                            },
                        ],
                    },
                ],
                "reactions": [{"name": "eyes", "users": ["U01E8P3JKM1"], "count": 1}],
            },
            "rendered": (
                # Should be just <emoji>
                "\U0001f604 <[color darkgray]>[\U0001f4401]<[color reset]>"
            ),
        },
        {
            "input_message": {
                "blocks": [
                    {
                        "type": "rich_text",
                        "block_id": "5Cg6",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [
                                    {
                                        "type": "emoji",
                                        "name": "smile",
                                        "unicode": "1f604",
                                    }
                                ],
                            },
                        ],
                    },
                ],
                "reactions": [{"name": "eyes", "users": ["U01E8P3JKM1"], "count": 1}],
            },
            "rendered": (
                # Should be just :<emoji name>:
                ":smile: <[color darkgray]>[:eyes:1]<[color reset]>"
            ),
            "render_emoji_as_string": True,
        },
        {
            "input_message": {
                "blocks": [
                    {
                        "type": "rich_text",
                        "block_id": "5Cg6",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [
                                    {
                                        "type": "emoji",
                                        "name": "smile",
                                        "unicode": "1f604",
                                    }
                                ],
                            },
                        ],
                    },
                ],
                "reactions": [{"name": "eyes", "users": ["U01E8P3JKM1"], "count": 1}],
            },
            "rendered": (
                # Should be <emoji> (:<emoji name>:)
                "\U0001f604 (:smile:) <[color darkgray]>[\U0001f440 (:eyes:)1]<[color reset]>"
            ),
            "render_emoji_as_string": "both",
        },
        {
            "input_message": {
                "text": "test",
                "reactions": [{"name": "custom", "users": ["U01E8P3JKM1"], "count": 2}],
            },
            "rendered": "test <[color darkgray]>[:custom:2]<[color reset]>",
        },
        {
            "input_message": {
                "text": "test",
                "reactions": [{"name": "custom", "users": ["U407ABLLW"], "count": 1}],
            },
            "rendered": "test <[color darkgray]>[:custom:(@alice)]<[color reset]>",
            "show_reaction_nicks": True,
        },
        {
            "input_message": {
                "text": "test",
                "reactions": [{"name": "custom", "users": ["U407ABLLW"], "count": 2}],
            },
            "rendered": "test <[color darkgray]>[:custom:(@alice, and others)]<[color reset]>",
            "show_reaction_nicks": True,
        },
        {
            "input_message": {
                "blocks": [
                    {
                        "type": "rich_text",
                        "block_id": "ASgLI",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [
                                    {"type": "text", "text": "<text> & "},
                                    {
                                        "type": "link",
                                        "url": "https://text.link?x=<x>&z=z",
                                    },
                                    {"type": "text", "text": " "},
                                    {
                                        "type": "text",
                                        "text": "<code> & ",
                                        "style": {"code": True},
                                    },
                                    {
                                        "type": "link",
                                        "url": "https://code.link?x=<x>&z=z",
                                        "style": {"code": True},
                                    },
                                    {"type": "text", "text": "\n"},
                                ],
                            },
                            {
                                "type": "rich_text_preformatted",
                                "elements": [
                                    {"type": "text", "text": "<code block> & "},
                                    {
                                        "type": "link",
                                        "url": "https://codeblock.link?x=<x>&z=z",
                                    },
                                ],
                                "border": 0,
                            },
                        ],
                    }
                ],
            },
            "rendered": (
                "<text> & https://text.link?x=<x>&z=z `<code> & https://code.link?x=<x>&z=z`\n"
                "```\n<code block> & https://codeblock.link?x=<x>&z=z\n```"
            ),
            "render_emoji_as_string": "both",
        },
    ],
)
def test_render_message(case, channel_general):
    wee_slack.EMOJI, wee_slack.EMOJI_WITH_SKIN_TONES_REVERSE = wee_slack.load_emoji()
    wee_slack.config.render_emoji_as_string = case.get("render_emoji_as_string")
    wee_slack.config.show_reaction_nicks = case.get("show_reaction_nicks", False)
    message_json = {"ts": str(wee_slack.SlackTS()), **case["input_message"]}
    message = wee_slack.SlackMessage("normal", message_json, channel_general)
    result = message.render()
    assert result == case["rendered"]

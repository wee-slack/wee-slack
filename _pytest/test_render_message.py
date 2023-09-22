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
    ],
)
def test_render_message(case, channel_general):
    wee_slack.EMOJI, wee_slack.EMOJI_WITH_SKIN_TONES_REVERSE = wee_slack.load_emoji()
    wee_slack.config.render_emoji_as_string = case.get("render_emoji_as_string")
    message_json = {"ts": str(wee_slack.SlackTS()), **case["input_message"]}
    message = wee_slack.SlackMessage("normal", message_json, channel_general)
    result = message.render()
    assert result == case["rendered"]

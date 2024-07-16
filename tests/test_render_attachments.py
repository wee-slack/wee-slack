from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Literal

import pytest

from slack.shared import shared
from slack.slack_message import SlackMessage
from tests.conftest import (
    channel_public_id,
    color_default,
    color_user_mention,
    resolve_pending_message_item,
    user_test1_id,
    workspace_id,
)

if TYPE_CHECKING:
    from typing_extensions import NotRequired, TypedDict
else:
    TypedDict = object


class Case(TypedDict):
    input_message: Any
    input_text_before: str
    output: str
    link_previews: NotRequired[Literal["always", "only_internal", "never"]]


cases: List[Case] = [
    {
        "input_message": {
            "attachments": [
                {
                    "title": "Title",
                }
            ]
        },
        "input_text_before": "",
        "output": "| Title",
    },
    {
        "input_message": {
            "attachments": [
                {
                    "title": "Title",
                }
            ]
        },
        "input_text_before": "Text before",
        "output": "\n".join(
            [
                "",
                "| Title",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "title": "Title1",
                },
                {
                    "title": "Title2",
                },
            ]
        },
        "input_text_before": "Text before",
        "output": "\n".join(
            [
                "",
                "| Title1",
                "| Title2",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "title": "Title",
                    "text": "Attachment text",
                    "title_link": "http://title.link",
                    "from_url": "http://from.url",
                    "fallback": "Fallback",
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "| Title (http://title.link)",
                "|  (http://from.url)",
                "| Attachment text",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "title": "Title",
                    "text": "Attachment text",
                    "title_link": "http://title.link",
                    "image_url": "http://image.url",
                    "fallback": "Fallback",
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "| Title (http://title.link)",
                "| Attachment text",
                "|  (http://image.url)",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "title": "Title",
                    "text": "Attachment text",
                    "title_link": "http://link1",
                    "from_url": "http://link2",
                    "image_url": "http://link3",
                }
            ]
        },
        "input_text_before": "http://link1 http://link2 http://link3",
        "output": "\n".join(
            [
                "",
                "| Title",
                "| Attachment text",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "title": "Title",
                    "text": "Attachment text",
                    "title_link": "http://link",
                    "from_url": "http://link",
                    "image_url": "http://link",
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "| Title (http://link)",
                "| Attachment text",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "title": "Title",
                    "text": "Attachment text",
                    "from_url": "http://link",
                    "image_url": "http://link",
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "| Title",
                "|  (http://link)",
                "| Attachment text",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "title": "Title",
                    "text": "Attachment text\n\n\nWith multiple lines",
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "| Title",
                "| Attachment text",
                "| With multiple lines",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "title": "Title",
                    "author_name": "Author",
                    "pretext": "Pretext",
                    "text": "Attachment text",
                    "title_link": "http://title.link",
                    "from_url": "http://from.url",
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "| Pretext",
                "| Author: Title (http://title.link)",
                "|  (http://from.url)",
                "| Attachment text",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "author_name": "Author",
                    "text": "Attachment text",
                    "title_link": "http://title.link",
                    "from_url": "http://from.url",
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "|  (http://from.url)",
                "| Author: Attachment text",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "fallback": "Fallback",
                }
            ]
        },
        "input_text_before": "",
        "output": "| Fallback",
    },
    {
        "input_message": {
            "attachments": [
                {
                    "fallback": "Fallback",
                    "title_link": "http://link",
                }
            ]
        },
        "input_text_before": "http://link",
        "output": "",
    },
    {
        "input_message": {
            "attachments": [
                {
                    "fallback": "Fallback",
                    "from_url": "http://link",
                }
            ]
        },
        "input_text_before": "http://link",
        "output": "",
    },
    {
        "input_message": {
            "attachments": [
                {
                    "fallback": "Fallback",
                    "image_url": "http://link",
                }
            ]
        },
        "input_text_before": "http://link",
        "output": "",
    },
    {
        "input_message": {
            "attachments": [{"text": "Some message", "footer": "Thread in #general"}]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "| Some message",
                "| Thread in #general",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "ts": 1584986782,
                    "text": "Some message",
                    "footer": "Thread in #general",
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "| Some message",
                "| Thread in #general | Mar 23, 2020",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "ts": "1584986782.261400",
                    "text": "Some message",
                    "footer": "Thread in #general",
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "| Some message",
                "| Thread in #general | Mar 23, 2020",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "text": "Original message",
                    "files": [
                        {
                            "id": "F12345678",
                            "title": "File",
                            "url_private": "http://link",
                        }
                    ],
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "| Original message",
                "| File (http://link)",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "title": "Title",
                    "fields": [
                        {
                            "title": "First field title",
                            "value": "First field value",
                        },
                        {
                            "title": "",
                            "value": "Second field value",
                        },
                    ],
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "| Title",
                "| First field title: First field value",
                "| Second field value",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "title": "First attachment title",
                    "text": "First attachment text",
                    "title_link": "http://title.link.1",
                    "from_url": "http://from.url.1",
                },
                {
                    "title": "Second attachment title",
                    "text": "Second attachment text",
                    "title_link": "http://title.link.2",
                    "from_url": "http://from.url.2",
                },
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "| First attachment title (http://title.link.1)",
                "|  (http://from.url.1)",
                "| First attachment text",
                "| Second attachment title (http://title.link.2)",
                "|  (http://from.url.2)",
                "| Second attachment text",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "title": "Title",
                    "color": "ff0000",
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                f"<[color:16711680]>|{color_default} Title",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "title": "Title",
                    "color": "#ff0000",
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                f"<[color:16711680]>|{color_default} Title",
            ]
        ),
    },
    {
        "input_message": {"attachments": [{"text": "Attachment text"}]},
        "input_text_before": "",
        "output": "| Attachment text",
        "link_previews": "always",
    },
    {
        "input_message": {
            "attachments": [
                {"text": "Attachment text", "original_url": "https://example.com"}
            ]
        },
        "input_text_before": "<https://example.com>",
        "output": "\n| Attachment text",
        "link_previews": "always",
    },
    {
        "input_message": {
            "attachments": [{"text": "Attachment text", "is_app_unfurl": True}]
        },
        "input_text_before": "",
        "output": "| Attachment text",
        "link_previews": "always",
    },
    {
        "input_message": {
            "attachments": [
                {
                    "text": "Attachment text",
                    "is_msg_unfurl": True,
                    "channel_id": channel_public_id,
                    "original_url": f"https://wee-slack-test.slack.com/archives/{channel_public_id}/p1721168022423289",
                }
            ]
        },
        "input_text_before": f"<https://wee-slack-test.slack.com/archives/{channel_public_id}/p1721168022423289>",
        "output": "\n".join(
            [
                "",
                "| Attachment text",
                f"| Posted in <[color:chat_channel]>#channel1{color_default}",
            ]
        ),
        "link_previews": "always",
    },
    {
        "input_message": {"attachments": [{"text": "Attachment text"}]},
        "input_text_before": "",
        "output": "| Attachment text",
        "link_previews": "only_internal",
    },
    {
        "input_message": {
            "attachments": [
                {"text": "Attachment text", "original_url": "https://example.com"}
            ]
        },
        "input_text_before": "<https://example.com>",
        "output": "",
        "link_previews": "only_internal",
    },
    {
        "input_message": {
            "attachments": [{"text": "Attachment text", "is_app_unfurl": True}]
        },
        "input_text_before": "",
        "output": "",
        "link_previews": "only_internal",
    },
    {
        "input_message": {
            "attachments": [
                {
                    "text": "Attachment text",
                    "is_msg_unfurl": True,
                    "channel_id": channel_public_id,
                    "original_url": f"https://wee-slack-test.slack.com/archives/{channel_public_id}/p1721168022423289",
                }
            ]
        },
        "input_text_before": f"<https://wee-slack-test.slack.com/archives/{channel_public_id}/p1721168022423289>",
        "output": "\n".join(
            [
                "",
                "| Attachment text",
                f"| Posted in <[color:chat_channel]>#channel1{color_default}",
            ]
        ),
        "link_previews": "only_internal",
    },
    {
        "input_message": {"attachments": [{"text": "Attachment text"}]},
        "input_text_before": "",
        "output": "| Attachment text",
        "link_previews": "never",
    },
    {
        "input_message": {
            "attachments": [
                {"text": "Attachment text", "original_url": "https://example.com"}
            ]
        },
        "input_text_before": "<https://example.com>",
        "output": "",
        "link_previews": "never",
    },
    {
        "input_message": {
            "attachments": [{"text": "Attachment text", "is_app_unfurl": True}]
        },
        "input_text_before": "",
        "output": "",
        "link_previews": "never",
    },
    {
        "input_message": {
            "attachments": [
                {
                    "text": "Attachment text",
                    "is_msg_unfurl": True,
                    "channel_id": channel_public_id,
                    "original_url": f"https://wee-slack-test.slack.com/archives/{channel_public_id}/p1721168022423289",
                }
            ]
        },
        "input_text_before": f"<https://wee-slack-test.slack.com/archives/{channel_public_id}/p1721168022423289>",
        "output": "",
        "link_previews": "never",
    },
    {
        "input_message": {
            "attachments": [
                {
                    "id": 1,
                    "ts": 1697480778,
                    "fallback": "title &amp; &lt;asd&gt;",
                    "text": "text &amp; &lt;asd&gt;",
                    "pretext": "pretext &amp; &lt;asd&gt;",
                    "title": "title &amp; &lt;asd&gt;",
                    "title_link": "https://title.link/?x=<x>&z=z",
                    "author_name": "author_name &amp; &lt;asd&gt;",
                    "from_url": "https://from.url/?x=<x>&z=z",
                    "image_url": "https://image.url/?x=<x>&z=z",
                    "footer": "footer &amp; &lt;asd&gt;",
                    "fields": [
                        {
                            "value": "field value &amp; &lt;asd&gt;",
                            "title": "field title &amp; &lt;asd&gt;",
                            "short": False,
                        },
                        {
                            "value": f"field value mention <@{user_test1_id}>",
                            "title": f"field title mention &lt;@{user_test1_id}&gt;",
                            "short": False,
                        },
                    ],
                },
                {
                    "id": 2,
                    "blocks": [
                        {
                            "type": "rich_text",
                            "block_id": "IQm+Q",
                            "elements": [
                                {
                                    "type": "rich_text_preformatted",
                                    "elements": [
                                        {
                                            "type": "text",
                                            "text": "block rich_text_preformatted & <asd>",
                                        }
                                    ],
                                }
                            ],
                        },
                        {
                            "type": "rich_text",
                            "block_id": "a5bVo",
                            "elements": [
                                {
                                    "type": "rich_text_section",
                                    "elements": [
                                        {
                                            "type": "text",
                                            "text": "block rich_text_section & <asd> ",
                                        },
                                        {
                                            "type": "link",
                                            "url": "https://block.link?x=<x>&z=z",
                                            "style": {"code": True},
                                        },
                                    ],
                                }
                            ],
                        },
                        {
                            "type": "rich_text",
                            "block_id": "FeChA",
                            "elements": [
                                {
                                    "type": "rich_text_section",
                                    "elements": [
                                        {"type": "user", "user_id": user_test1_id},
                                        {"type": "text", "text": ": <@ASD>"},
                                    ],
                                }
                            ],
                        },
                    ],
                    "fallback": "[no preview available]",
                },
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "| pretext & <asd>",
                "| author_name & <asd>: title & <asd> (https://title.link/?x=<x>&z=z)",
                "|  (https://from.url/?x=<x>&z=z)",
                "| text & <asd>",
                "|  (https://image.url/?x=<x>&z=z)",
                "| field title & <asd>: field value & <asd>",
                f"| field title mention <@{user_test1_id}>: field value mention {color_user_mention}@Test_1{color_default}",
                "| footer & <asd> | Oct 16, 2023",
                "| ```",
                "| block rich_text_preformatted & <asd>",
                "| ```",
                "| block rich_text_section & <asd> `https://block.link?x=<x>&z=z`",
                f"| {color_user_mention}@Test_1{color_default}: <@ASD>",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "from_url": "https://from.url",
                    "ts": "1697393234.859799",
                    "author_id": user_test1_id,
                    "channel_id": channel_public_id,
                    "channel_team": workspace_id,
                    "is_msg_unfurl": True,
                    "id": 1,
                    "fallback": "[October 15th, 2023 11:07 AM] username: fallback text",
                    "text": "text",
                    "author_name": "Author name",
                    "author_link": f"https://wee-slack-test.slack.com/team/{user_test1_id}",
                    "mrkdwn_in": ["text"],
                    "footer": "Slack Conversation",
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "|  (https://from.url)",
                "| Author name: text",
                f"| Posted in <[color:chat_channel]>#channel1{color_default} | Oct 15, 2023",
            ]
        ),
    },
    {
        "input_message": {
            "attachments": [
                {
                    "from_url": "https://from.url",
                    "ts": "1697393234.859799",
                    "author_id": user_test1_id,
                    "channel_id": channel_public_id,
                    "channel_team": workspace_id,
                    "is_msg_unfurl": True,
                    "is_reply_unfurl": True,
                    "id": 1,
                    "fallback": "[October 15th, 2023 11:07 AM] username: fallback text",
                    "text": "text",
                    "author_name": "Author name",
                    "author_link": f"https://wee-slack-test.slack.com/team/{user_test1_id}",
                    "mrkdwn_in": ["text"],
                    "footer": "Thread in Slack Conversation",
                }
            ]
        },
        "input_text_before": "",
        "output": "\n".join(
            [
                "|  (https://from.url)",
                "| Author name: text",
                f"| From a thread in <[color:chat_channel]>#channel1{color_default} | Oct 15, 2023",
            ]
        ),
    },
]


@pytest.mark.parametrize("case", cases)
def test_render_attachments(case: Case, message1_in_channel_public: SlackMessage):
    shared.config.look.render_url_as.value = "${text} (${url})"
    shared.config.look.display_link_previews.value = case.get("link_previews", "always")
    message1_in_channel_public.update_message_json(case["input_message"])
    parsed = message1_in_channel_public._render_attachments(  # pyright: ignore [reportPrivateUsage]
        [case["input_text_before"]]
    )
    resolved = "".join(resolve_pending_message_item(item) for item in parsed)
    assert resolved == case["output"]

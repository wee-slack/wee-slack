from __future__ import print_function, unicode_literals

import wee_slack
import pytest


@pytest.mark.parametrize(
    "case",
    (
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
                    "| http://from.url",
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
                    "| http://image.url",
                ]
            ),
        },
        {
            "input_message": {
                "attachments": [
                    {
                        "title": "Title",
                        "text": "Attachment text",
                        "title_link": "http://link?a=1&b=2",
                        "from_url": "http://link?a=1&b=2",
                        "image_url": "http://link?a=1&b=2",
                    }
                ]
            },
            "input_text_before": "http://link?a=1&b=2",
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
                    "| http://link",
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
                    "| http://from.url",
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
                    "| http://from.url",
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
                "attachments": [
                    {"text": "Some message", "footer": "Thread in #general"}
                ]
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
                    "| http://link (File)",
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
                    "| http://from.url.1",
                    "| First attachment text",
                    "| Second attachment title (http://title.link.2)",
                    "| http://from.url.2",
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
                    "<[color 16711680]>|<[color reset]> Title",
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
                    "<[color 16711680]>|<[color reset]> Title",
                ]
            ),
        },
        {
            "input_message": {
                "attachments": [
                    {
                        "text": "Attachment text",
                        "original_url": "http://from.url",
                    }
                ]
            },
            "input_text_before": "",
            "output": "\n".join(
                [
                    "| Attachment text",
                ]
            ),
            "link_previews": True,
        },
        {
            "input_message": {
                "attachments": [
                    {
                        "text": "Attachment text",
                        "original_url": "http://from.url",
                    }
                ]
            },
            "input_text_before": "",
            "output": "",
            "link_previews": False,
        },
        {
            "input_message": {
                "attachments": [
                    {
                        "text": "Attachment text",
                    }
                ]
            },
            "input_text_before": "",
            "output": "\n".join(
                [
                    "| Attachment text",
                ]
            ),
            "link_previews": False,
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
                                "value": "field value mention <@U407ABLLW>",
                                "title": "field title mention &lt;@U407ABLLW&gt;",
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
                                            {"type": "user", "user_id": "U407ABLLW"},
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
                    "| https://from.url/?x=<x>&z=z",
                    "| text & <asd>",
                    "| https://image.url/?x=<x>&z=z",
                    "| field title & <asd>: field value & <asd>",
                    "| field title mention <@U407ABLLW>: field value mention @alice",
                    "| footer & <asd> | Oct 16, 2023",
                    "| ```",
                    "| block rich_text_preformatted & <asd>",
                    "| ```",
                    "| block rich_text_section & <asd> `https://block.link?x=<x>&z=z`",
                    "| @alice: <@ASD>",
                ]
            ),
        },
    ),
)
def test_unwrap_attachments(case, channel_general):
    wee_slack.config.link_previews = case.get("link_previews")
    message_json = {"ts": str(wee_slack.SlackTS()), **case["input_message"]}
    message = wee_slack.SlackMessage("normal", message_json, channel_general)
    result = wee_slack.unwrap_attachments(message, case["input_text_before"])
    assert result == case["output"]

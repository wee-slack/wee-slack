from __future__ import annotations

from typing import TYPE_CHECKING, List

import pytest

from slack.shared import shared
from slack.slack_message import SlackMessage
from tests.conftest import (
    color_default,
    color_user_mention,
    resolve_pending_message_item,
    user_test1_id,
)

if TYPE_CHECKING:
    from slack_api.slack_conversations_history import SlackMessageBlock
    from typing_extensions import TypedDict
else:
    TypedDict = object


class Case(TypedDict):
    blocks: List[SlackMessageBlock]
    rendered: List[str]


cases: List[Case] = [
    {
        "blocks": [
            {
                "type": "rich_text",
                "block_id": "dhGA",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {"type": "text", "text": "normal "},
                            {
                                "type": "text",
                                "text": "bold",
                                "style": {"bold": True},
                            },
                            {"type": "text", "text": " "},
                            {
                                "type": "text",
                                "text": "italic",
                                "style": {"italic": True},
                            },
                            {"type": "text", "text": " "},
                            {
                                "type": "text",
                                "text": "strikethrough",
                                "style": {"strike": True},
                            },
                            {"type": "text", "text": " "},
                            {
                                "type": "text",
                                "text": "bold-italic-strikethrough",
                                "style": {
                                    "bold": True,
                                    "italic": True,
                                    "strike": True,
                                },
                            },
                            {"type": "text", "text": " "},
                            {
                                "type": "link",
                                "url": "https://vg.no",
                                "text": "link",
                            },
                            {"type": "text", "text": "\n"},
                        ],
                    },
                    {
                        "type": "rich_text_list",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [{"type": "text", "text": "number"}],
                            },
                            {
                                "type": "rich_text_section",
                                "elements": [{"type": "text", "text": "list"}],
                            },
                        ],
                        "style": "ordered",
                        "indent": 0,
                        "border": 0,
                    },
                    {
                        "type": "rich_text_quote",
                        "elements": [
                            {"type": "text", "text": "some quote\nmore quote"}
                        ],
                    },
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {
                                "type": "text",
                                "text": "inline code",
                                "style": {"code": True},
                            },
                            {"type": "text", "text": "\n"},
                        ],
                    },
                    {
                        "type": "rich_text_preformatted",
                        "elements": [{"type": "text", "text": "block code\nmore code"}],
                        "border": 0,
                    },
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {"type": "user", "user_id": user_test1_id},
                            {"type": "text", "text": ": "},
                            {
                                "type": "emoji",
                                "name": "open_mouth",
                                "unicode": "1f62e",
                            },
                        ],
                    },
                ],
            }
        ],
        "rendered": [
            "normal <[color:bold]>*bold*<[color:-bold]> <[color:italic]>_italic_"
            "<[color:-italic]> ~strikethrough~ <[color:bold]><[color:italic]>"
            "*_~bold-italic-strikethrough~_*<[color:-italic]><[color:-bold]> "
            "link (https://vg.no)",
            "1. number",
            "2. list",
            "> some quote",
            "> more quote",
            "`inline code`",
            "```",
            "block code",
            "more code",
            "```",
            f"{color_user_mention}@Test_1{color_default}: 😮",
        ],
    },
    {
        "blocks": [
            {
                "type": "rich_text",
                "block_id": "D=pkP",
                "elements": [
                    {
                        "type": "rich_text_list",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [{"type": "text", "text": "number"}],
                            }
                        ],
                        "style": "ordered",
                        "indent": 0,
                        "border": 0,
                    },
                    {
                        "type": "rich_text_list",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [{"type": "text", "text": "list"}],
                            }
                        ],
                        "style": "ordered",
                        "indent": 1,
                        "border": 0,
                    },
                    {
                        "type": "rich_text_list",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [{"type": "text", "text": "third"}],
                            }
                        ],
                        "style": "ordered",
                        "indent": 2,
                        "border": 0,
                    },
                    {
                        "type": "rich_text_list",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [
                                    {"type": "text", "text": "end number list"}
                                ],
                            }
                        ],
                        "style": "ordered",
                        "indent": 0,
                        "offset": 1,
                        "border": 0,
                    },
                    {
                        "type": "rich_text_list",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [{"type": "text", "text": "bullet"}],
                            }
                        ],
                        "style": "bullet",
                        "indent": 0,
                        "border": 0,
                    },
                    {
                        "type": "rich_text_list",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [{"type": "text", "text": "list"}],
                            }
                        ],
                        "style": "bullet",
                        "indent": 1,
                        "border": 0,
                    },
                    {
                        "type": "rich_text_list",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [{"type": "text", "text": "third"}],
                            }
                        ],
                        "style": "bullet",
                        "indent": 2,
                        "border": 0,
                    },
                    {
                        "type": "rich_text_list",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [
                                    {"type": "text", "text": "end bullet list"}
                                ],
                            }
                        ],
                        "style": "bullet",
                        "indent": 0,
                        "border": 0,
                    },
                ],
            }
        ],
        "rendered": [
            "1. number",
            "    a. list",
            "        i. third",
            "2. end number list",
            "• bullet",
            "    ◦ list",
            "        ▪︎ third",
            "• end bullet list",
        ],
    },
    {
        "blocks": [
            {
                "type": "rich_text",
                "block_id": "usQpu",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {
                                "type": "text",
                                "text": "test ",
                                "style": {"code": True},
                            },
                            {
                                "type": "link",
                                "url": "http://asdf.de",
                                "text": "asdf.de",
                                "style": {"code": True},
                            },
                            {
                                "type": "text",
                                "text": " asdf.de:443",
                                "style": {"code": True},
                            },
                            {"type": "text", "text": "\n"},
                        ],
                    },
                    {
                        "type": "rich_text_preformatted",
                        "elements": [{"type": "text", "text": "asdf.de\nasdf.de:443"}],
                        "border": 0,
                    },
                ],
            }
        ],
        "rendered": [
            "`test asdf.de asdf.de:443`",
            "```",
            "asdf.de",
            "asdf.de:443",
            "```",
        ],
    },
    {
        "blocks": [
            {
                "type": "rich_text",
                "block_id": "vLtn",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {
                                "type": "text",
                                "text": "bold ",
                                "style": {"bold": True},
                            },
                            {
                                "type": "text",
                                "text": "code ",
                                "style": {"bold": True, "code": True},
                            },
                            {
                                "type": "text",
                                "text": "not bold ",
                                "style": {"code": True},
                            },
                            {
                                "type": "text",
                                "text": "italic",
                                "style": {"italic": True, "code": True},
                            },
                            {
                                "type": "text",
                                "text": " text",
                                "style": {"italic": True},
                            },
                        ],
                    }
                ],
            }
        ],
        "rendered": [
            "<[color:bold]>*bold `code *<[color:-bold]>not bold <[color:italic]>_italic` text_<[color:-italic]>",
        ],
    },
    {
        "blocks": [
            {
                "type": "rich_text",
                "block_id": "28L",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {
                                "type": "text",
                                "text": "bold and italic combined",
                                "style": {"bold": True, "italic": True},
                            }
                        ],
                    }
                ],
            }
        ],
        "rendered": [
            "<[color:bold]><[color:italic]>*_bold and italic combined_*<[color:-italic]><[color:-bold]>"
        ],
    },
    {
        "blocks": [
            {
                "type": "rich_text",
                "block_id": "tm5d+",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {
                                "type": "text",
                                "text": "foo",
                                "style": {"italic": True, "code": True},
                            },
                            {
                                "type": "text",
                                "text": "bar",
                                "style": {"bold": True, "code": True},
                            },
                        ],
                    }
                ],
            }
        ],
        "rendered": [
            "<[color:italic]>`_foo_<[color:-italic]><[color:bold]>*bar*`<[color:-bold]>"
        ],
    },
    {
        "blocks": [
            {
                "type": "rich_text",
                "block_id": "A+l5x",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {
                                "type": "text",
                                "text": "all styles",
                                "style": {
                                    "bold": True,
                                    "italic": True,
                                    "strike": True,
                                    "code": True,
                                },
                            }
                        ],
                    }
                ],
            }
        ],
        "rendered": [
            "<[color:bold]><[color:italic]>`*_~all styles~_*`<[color:-italic]><[color:-bold]>"
        ],
    },
    {
        "blocks": [
            {
                "type": "rich_text",
                "block_id": "M23r4",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [{"type": "color", "value": "#FFAA00"}],
                    }
                ],
            }
        ],
        "rendered": [f"#FFAA00 <[color:16755200]>■{color_default}"],
    },
    {
        "blocks": [
            {
                "type": "rich_text",
                "block_id": "fZUc/",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {
                                "type": "link",
                                "url": "https://example.com/?a=1&amp;b=2",
                                "text": "test",
                            }
                        ],
                    }
                ],
            }
        ],
        "rendered": ["test (https://example.com/?a=1&b=2)"],
    },
    {
        "blocks": [
            {
                "type": "rich_text",
                "block_id": "fZUc/",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {
                                "type": "link",
                                "url": "https://example.com/?a=1&amp;b=2",
                                "style": {"code": True},
                            }
                        ],
                    }
                ],
            }
        ],
        "rendered": ["`https://example.com/?a=1&amp;b=2`"],
    },
]


@pytest.mark.parametrize("case", cases)
def test_render_blocks(case: Case, message1_in_channel_public: SlackMessage):
    shared.config.look.render_url_as.value = "${text} (${url})"
    parsed = message1_in_channel_public._render_blocks(  # pyright: ignore [reportPrivateUsage]
        case["blocks"]
    )
    resolved = "".join(resolve_pending_message_item(item) for item in parsed)
    assert resolved.split("\n") == case["rendered"]

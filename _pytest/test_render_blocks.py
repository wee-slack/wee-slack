from __future__ import print_function, unicode_literals

import pytest

import wee_slack


@pytest.mark.parametrize(
    "case",
    [
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
                            "elements": [
                                {"type": "text", "text": "block code\nmore code"}
                            ],
                            "border": 0,
                        },
                        {
                            "type": "rich_text_section",
                            "elements": [
                                {"type": "user", "user_id": "U407ABLLW"},
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
                "normal <[color bold]>*bold*<[color -bold]> <[color italic]>_italic_"
                "<[color -italic]> ~strikethrough~ <[color bold]><[color italic]>"
                "*_~bold-italic-strikethrough~_*<[color -italic]><[color -bold]> "
                "https://vg.no (link)",
                "1. number",
                "2. list",
                "> some quote",
                "> more quote",
                "`inline code`",
                "```\nblock code\nmore code\n```",
                "@alice: :open_mouth:",
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
                            "elements": [
                                {"type": "text", "text": "asdf.de\nasdf.de:443"}
                            ],
                            "border": 0,
                        },
                    ],
                }
            ],
            "rendered": [
                "`test asdf.de asdf.de:443`",
                "```\nasdf.de\nasdf.de:443\n```",
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
                "<[color bold]>*bold `code *<[color -bold]>not bold <[color italic]>_italic` text_<[color -italic]>",
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
                "<[color bold]><[color italic]>*_bold and italic combined_*<[color -italic]><[color -bold]>"
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
            "rendered": ["#FFAA00 <[color 16755200]>■<[color reset]>"],
        },
    ],
)
def test_render_blocks(case):
    assert wee_slack.unfurl_blocks(case["blocks"]) == case["rendered"]

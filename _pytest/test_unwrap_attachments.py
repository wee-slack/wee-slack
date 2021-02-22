from __future__ import print_function, unicode_literals

import wee_slack
import pytest


@pytest.mark.parametrize('case', (
    {
        'input_message': {'attachments': [{
            'title': 'Title',
        }]},
        'input_text_before': "Text before",
        'output': "\n".join([
            "",
            "| Title",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'Title',
            'text': 'Attachment text',
            'title_link': 'http://title.link',
            'from_url': 'http://from.url',
            'fallback': 'Fallback',
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| Title (http://title.link)",
            "| http://from.url",
            "| Attachment text",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'Title',
            'text': 'Attachment text',
            'title_link': 'http://title.link',
            'image_url': 'http://image.url',
            'fallback': 'Fallback',
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| Title (http://title.link)",
            "| Attachment text",
            "| http://image.url",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'Title',
            'text': 'Attachment text',
            'title_link': 'http://link?a=1&b=2',
            'from_url': 'http://link?a=1&b=2',
            'image_url': 'http://link?a=1&b=2',
        }]},
        'input_text_before': "http://link?a=1&amp;b=2",
        'output': "\n".join([
            "",
            "| Title",
            "| Attachment text",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'Title',
            'text': 'Attachment text',
            'title_link': 'http://link?a=1&amp;b=2',
            'from_url': 'http://link?a=1&amp;b=2',
            'image_url': 'http://link?a=1&amp;b=2',
        }]},
        'input_text_before': "http://link?a=1&amp;b=2",
        'output': "\n".join([
            "",
            "| Title",
            "| Attachment text",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'Title',
            'text': 'Attachment text',
            'title_link': 'http://link',
            'from_url': 'http://link',
            'image_url': 'http://link',
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| Title (http://link)",
            "| Attachment text",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'Title',
            'text': 'Attachment text',
            'from_url': 'http://link',
            'image_url': 'http://link',
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| Title",
            "| http://link",
            "| Attachment text",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'Title',
            'text': 'Attachment text\n\n\nWith multiple lines',
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| Title",
            "| Attachment text",
            "| With multiple lines",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'Title',
            'author_name': 'Author',
            'pretext': 'Pretext',
            'text': 'Attachment text',
            'title_link': 'http://title.link',
            'from_url': 'http://from.url',
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| Pretext",
            "| Author: Title (http://title.link)",
            "| http://from.url",
            "| Attachment text",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'author_name': 'Author',
            'text': 'Attachment text',
            'title_link': 'http://title.link',
            'from_url': 'http://from.url',
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| http://from.url",
            "| Author: Attachment text",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'fallback': 'Fallback',
        }]},
        'input_text_before': "",
        'output': "| Fallback",
    },
    {
        'input_message': {'attachments': [{
            'fallback': 'Fallback',
            'title_link': 'http://link',
        }]},
        'input_text_before': "http://link",
        'output': "",
    },
    {
        'input_message': {'attachments': [{
            'fallback': 'Fallback',
            'from_url': 'http://link',
        }]},
        'input_text_before': "http://link",
        'output': "",
    },
    {
        'input_message': {'attachments': [{
            'fallback': 'Fallback',
            'image_url': 'http://link',
        }]},
        'input_text_before': "http://link",
        'output': "",
    },
    {
        'input_message': {'attachments': [{
            'text': 'Some message',
            'footer': 'Thread in #general'
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| Some message",
            "| Thread in #general",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'ts': 1584986782,
            'text': 'Some message',
            'footer': 'Thread in #general'
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| Some message",
            "| Thread in #general | Mar 23, 2020",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'ts': '1584986782.261400',
            'text': 'Some message',
            'footer': 'Thread in #general'
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| Some message",
            "| Thread in #general | Mar 23, 2020",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'text': 'Original message',
            'files': [
              {
                'title': 'File',
                'url_private': 'http://link',
              }
            ],
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| Original message",
            "| http://link (File)",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'Title',
            'fields': [{
                'title': 'First field title',
                'value': 'First field value',
            }, {
                'title': '',
                'value': 'Second field value',
            }],
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| Title",
            "| First field title: First field value",
            "| Second field value",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'First attachment title',
            'text': 'First attachment text',
            'title_link': 'http://title.link.1',
            'from_url': 'http://from.url.1',
        }, {
            'title': 'Second attachment title',
            'text': 'Second attachment text',
            'title_link': 'http://title.link.2',
            'from_url': 'http://from.url.2',
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| First attachment title (http://title.link.1)",
            "| http://from.url.1",
            "| First attachment text",
            "| Second attachment title (http://title.link.2)",
            "| http://from.url.2",
            "| Second attachment text",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'Title',
            'color': 'ff0000',
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "<[color 16711680]>|<[color reset]> Title",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'Title',
            'color': '#ff0000',
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "<[color 16711680]>|<[color reset]> Title",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'text': 'Attachment text',
            'original_url': 'http://from.url',
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| Attachment text",
        ]),
        'link_previews': True
    },
    {
        'input_message': {'attachments': [{
            'text': 'Attachment text',
            'original_url': 'http://from.url',
        }]},
        'input_text_before': "",
        'output': '',
        'link_previews': False
    },
    {
        'input_message': {'attachments': [{
            'text': 'Attachment text',
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "| Attachment text",
        ]),
        'link_previews': False
    },
))
def test_unwrap_attachments(case):
    wee_slack.config.link_previews = case.get('link_previews')
    result = wee_slack.unwrap_attachments(
        case['input_message'], case['input_text_before'])
    assert result == case['output']

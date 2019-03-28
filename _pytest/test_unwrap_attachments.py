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
            "Title",
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
            "Title (http://title.link)",
            "http://from.url",
            "Attachment text",
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
            "Title (http://title.link)",
            "Attachment text",
            "http://image.url",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'Title',
            'text': 'Attachment text',
            'title_link': 'http://link?a=1&b=2',
            'from_url': 'http://link?a=1&b=2',
        }]},
        'input_text_before': "http://link?a=1&amp;b=2",
        'output': "\n".join([
            "",
            "Title",
            "Attachment text",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'Title',
            'text': 'Attachment text',
            'title_link': 'http://link',
            'from_url': 'http://link',
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "Title (http://link)",
            "Attachment text",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'title': 'Title',
            'text': 'Attachment text\n\n\nWith multiple lines',
        }]},
        'input_text_before': "",
        'output': "\n".join([
            "Title",
            "Attachment text\nWith multiple lines",
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
            "Pretext",
            "Author: Title (http://title.link)",
            "http://from.url",
            "Attachment text",
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
            "http://from.url",
            "Author: Attachment text",
        ]),
    },
    {
        'input_message': {'attachments': [{
            'fallback': 'Fallback',
        }]},
        'input_text_before': "",
        'output': "Fallback",
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
            "Title",
            "First field title First field value",
            "Second field value",
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
            "First attachment title (http://title.link.1)",
            "http://from.url.1",
            "First attachment text",
            "Second attachment title (http://title.link.2)",
            "http://from.url.2",
            "Second attachment text",
        ]),
    },
))
def test_unwrap_attachments(case):
    result = wee_slack.unwrap_attachments(
        case['input_message'], case['input_text_before'])
    assert result == case['output']

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
            'title_link': 'http://link',
            'from_url': 'http://link',
        }]},
        'input_text_before': "http://link",
        'output': "\n".join([
            "",
            "Title",
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
))
def test_unwrap_attachments(case):
    result = wee_slack.unwrap_attachments(
        case['input_message'], case['input_text_before'])
    assert result == case['output']

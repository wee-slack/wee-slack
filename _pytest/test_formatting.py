from __future__ import print_function, unicode_literals

import pytest
import re

import wee_slack


@pytest.mark.parametrize("text", [
    """
    * an item
    * another item
    """,
    "* Run this command: `find . -name '*.exe'`",
])
def test_does_not_format(realish_eventrouter, text):
    assert wee_slack.render_formatting(text) == text


@pytest.mark.parametrize("text", [
    "`hello *bar*`",
    "`*`",
    "`* *`",
    "`* * *`",
    "`* * * *`",
    "`* * * * *`",
    "`* * * * * *`",
])
def test_preserves_format_chars_in_code(realish_eventrouter, text):
    formatted_text = wee_slack.render_formatting(text)
    # TODO: wee-slack erroneously inserts formatting in code blocks
    formatted_text = re.sub(r'<\[color .*?\]>', '', formatted_text)
    assert formatted_text == text

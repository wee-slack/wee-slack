import pytest

import wee_slack


@pytest.mark.parametrize("text", [
    """
    * an item
    * another item
    """,
    "* Run this command: `find . -name '*.exe'`",
])
def test_does_not_format(text):
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
def test_preserves_format_chars_in_code(text):
    assert wee_slack.render_formatting(text) == text

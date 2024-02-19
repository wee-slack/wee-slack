from __future__ import annotations

from typing import TYPE_CHECKING, List

import pytest

from slack.slack_message import SlackMessage
from tests.conftest import (
    channel_public_id,
    color_channel_mention,
    color_default,
    color_user_mention,
    color_usergroup_mention,
    resolve_pending_message_item,
    user_test1_id,
)

if TYPE_CHECKING:
    from typing_extensions import TypedDict
else:
    TypedDict = object


class Case(TypedDict):
    input: str
    output: str


cases: List[Case] = [
    {
        "input": "foo",
        "output": "foo",
    },
    {
        "input": "<!channel>",
        "output": f"{color_usergroup_mention}@channel{color_default}",
    },
    {
        "input": "<!here>",
        "output": f"{color_usergroup_mention}@here{color_default}",
    },
    {
        "input": f"<@{user_test1_id}|@othernick>: foo",
        "output": f"{color_user_mention}@Test_1{color_default}: foo",
    },
    {
        "input": f"foo <#{channel_public_id}|otherchannel> bar",
        "output": f"foo {color_channel_mention}#channel1{color_default} bar",
    },
]


@pytest.mark.parametrize("case", cases)
def test_unfurl_refs(case: Case, message1_in_channel_public: SlackMessage):
    parsed = message1_in_channel_public._unfurl_refs(  # pyright: ignore [reportPrivateUsage]
        case["input"]
    )
    resolved = "".join(resolve_pending_message_item(item) for item in parsed)
    assert resolved == case["output"]

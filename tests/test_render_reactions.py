from __future__ import annotations

from typing import TYPE_CHECKING, List

import pytest

from slack.shared import shared
from slack.slack_message import SlackMessage
from tests.conftest import (
    color_default,
    user_test1_id,
    user_test2_id,
)

if TYPE_CHECKING:
    from slack_api.slack_conversations_history import SlackMessageReaction
    from typing_extensions import TypedDict
else:
    TypedDict = object


class Case(TypedDict):
    reactions: List[SlackMessageReaction]
    rendered: str
    display_reaction_nicks: bool


color_reaction_suffix = "<[color:<[config_color:reaction_suffix]>]>"
color_reaction_self_suffix = "<[color:<[config_color:reaction_self_suffix]>]>"

cases: List[Case] = [
    {
        "reactions": [{"name": "custom", "users": [user_test2_id], "count": 1}],
        "rendered": f" {color_reaction_suffix}[:custom:1]{color_default}",
        "display_reaction_nicks": False,
    },
    {
        "reactions": [{"name": "custom", "users": [user_test1_id], "count": 1}],
        "rendered": f" {color_reaction_suffix}[{color_reaction_self_suffix}:custom:1{color_reaction_suffix}]{color_default}",
        "display_reaction_nicks": False,
    },
    {
        "reactions": [{"name": "custom", "users": [user_test2_id], "count": 1}],
        "rendered": f" {color_reaction_suffix}[:custom:1(Test_2)]{color_default}",
        "display_reaction_nicks": True,
    },
    {
        "reactions": [{"name": "custom", "users": [user_test1_id], "count": 1}],
        "rendered": f" {color_reaction_suffix}[{color_reaction_self_suffix}:custom:1(Test_1){color_reaction_suffix}]{color_default}",
        "display_reaction_nicks": True,
    },
    {
        "reactions": [{"name": "custom", "users": [user_test2_id], "count": 2}],
        "rendered": f" {color_reaction_suffix}[:custom:2]{color_default}",
        "display_reaction_nicks": False,
    },
    {
        "reactions": [{"name": "custom", "users": [user_test2_id], "count": 2}],
        "rendered": f" {color_reaction_suffix}[:custom:2(Test_2, and others)]{color_default}",
        "display_reaction_nicks": True,
    },
]


@pytest.mark.parametrize("case", cases)
def test_create_reactions_string(case: Case, message1_in_channel_public: SlackMessage):
    shared.config.look.display_reaction_nicks.value = case["display_reaction_nicks"]
    message1_in_channel_public._message_json["reactions"] = case["reactions"]  # pyright: ignore [reportPrivateUsage]

    coroutine = message1_in_channel_public._create_reactions_string()  # pyright: ignore [reportPrivateUsage]
    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(None)
    assert excinfo.value.value == case["rendered"]

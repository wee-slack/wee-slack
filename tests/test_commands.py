# Test calling the correct function

from itertools import accumulate

from slack.commands import parse_options
from slack.shared import shared


def test_all_parent_commands_exist():
    for command in shared.commands:
        parents = accumulate(command.split(" "), lambda x, y: f"{x} {y}")
        for parent in parents:
            assert parent in shared.commands


def test_parse_options_without_options():
    pos_args, options = parse_options("workspace add wee-slack-test")
    assert pos_args == "workspace add wee-slack-test"
    assert options == {}


def test_parse_options_with_option():
    pos_args, options = parse_options("workspace add wee-slack-test -autoconnect")
    assert pos_args == "workspace add wee-slack-test"
    assert options == {"autoconnect": True}


def test_parse_options_option_in_middle():
    pos_args, options = parse_options("workspace add -autoconnect wee-slack-test")
    assert pos_args == "workspace add wee-slack-test"
    assert options == {"autoconnect": True}


def test_parse_options_option_with_value():
    pos_args, options = parse_options(
        "workspace add wee-slack-test -autoconnect -api_token=xoxp-1"
    )
    assert pos_args == "workspace add wee-slack-test"
    assert options == {"autoconnect": True, "api_token": "xoxp-1"}

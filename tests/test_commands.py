from __future__ import annotations

from itertools import accumulate

from slack.commands import parse_options
from slack.shared import shared

# TODO: Test calling the correct function


def test_all_parent_commands_exist():
    for command in shared.commands:
        parents = accumulate(command.split(" "), lambda x, y: f"{x} {y}")
        for parent in parents:
            assert parent in shared.commands


def test_parse_options_without_options():
    pos_args, options = parse_options("arg1 arg2", options_only_first=False)
    assert pos_args == "arg1 arg2"
    assert options == {}


def test_parse_options_with_option_first():
    pos_args, options = parse_options("-option1 arg1", options_only_first=False)
    assert pos_args == "arg1"
    assert options == {"option1": True}


def test_parse_options_with_option_last():
    pos_args, options = parse_options("arg1 -option1", options_only_first=False)
    assert pos_args == "arg1"
    assert options == {"option1": True}


def test_parse_options_with_option_in_middle():
    pos_args, options = parse_options("arg1 -option1 arg2", options_only_first=False)
    assert pos_args == "arg1 arg2"
    assert options == {"option1": True}


def test_parse_options_option_with_value():
    pos_args, options = parse_options(
        "arg1 -option1 -option2=value2", options_only_first=False
    )
    assert pos_args == "arg1"
    assert options == {"option1": True, "option2": "value2"}


def test_parse_options_without_options_only_first():
    pos_args, options = parse_options("arg1 arg2", options_only_first=True)
    assert pos_args == "arg1 arg2"
    assert options == {}


def test_parse_options_with_option_first_only_first():
    pos_args, options = parse_options("-option1 -option2 arg1", options_only_first=True)
    assert pos_args == "arg1"
    assert options == {"option1": True, "option2": True}


def test_parse_options_with_option_last_only_first():
    pos_args, options = parse_options("arg1 -option1", options_only_first=True)
    assert pos_args == "arg1 -option1"
    assert options == {}


def test_parse_options_with_option_in_middle_only_first():
    pos_args, options = parse_options("arg1 -option1 arg2", options_only_first=True)
    assert pos_args == "arg1 -option1 arg2"
    assert options == {}


def test_parse_options_option_with_value_only_first():
    pos_args, options = parse_options(
        "arg1 -option1 -option2=value2", options_only_first=True
    )
    assert pos_args == "arg1 -option1 -option2=value2"
    assert options == {}

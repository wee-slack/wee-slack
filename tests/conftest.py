from __future__ import annotations

import importlib
import importlib.machinery
import json
import sys
from typing import TYPE_CHECKING, Dict, Union

import pytest

if TYPE_CHECKING:
    from slack_api.slack_conversations_history import (
        SlackConversationsHistorySuccessResponse,
    )
    from slack_api.slack_conversations_info import (
        SlackConversationsInfo,
        SlackConversationsInfoSuccessResponse,
    )
    from slack_api.slack_users_info import SlackUserInfo, SlackUserInfoSuccessResponse


# Copied from https://stackoverflow.com/a/72721573
def import_stub(stubs_path: str, module_name: str):
    sys.path_hooks.insert(
        0,
        importlib.machinery.FileFinder.path_hook(
            (importlib.machinery.SourceFileLoader, [".pyi"])
        ),
    )
    sys.path.insert(0, stubs_path)

    try:
        return importlib.import_module(module_name)
    finally:
        sys.path.pop(0)
        sys.path_hooks.pop(0)


import_stub("typings", "weechat")

import weechat

from slack.config import SlackConfig
from slack.shared import shared
from slack.slack_conversation import SlackConversation
from slack.slack_emoji import load_standard_emojis
from slack.slack_message import PendingMessageItem, SlackMessage
from slack.slack_user import SlackUser
from slack.slack_workspace import SlackWorkspace
from slack.task import Future

config_values: Dict[str, str] = {
    "replace_space_in_nicks_with": "_",
}


def config_new_option(
    config_file: str,
    section: str,
    name: str,
    type: str,
    description: str,
    string_values: str,
    min: int,
    max: int,
    default_value: Union[str, None],
    value: Union[str, None],
    null_value_allowed: int,
    callback_check_value: str,
    callback_check_value_data: str,
    callback_change: str,
    callback_change_data: str,
    callback_delete: str,
    callback_delete_data: str,
) -> str:
    if name not in config_values and default_value is not None:
        config_values[name] = default_value
    return name


def config_option_set(option: str, value: str, run_callback: int) -> int:
    # TODO: special values
    old_value = config_values.get(option)
    if value == old_value:
        return weechat.WEECHAT_CONFIG_OPTION_SET_OK_SAME_VALUE
    config_values[option] = value
    return weechat.WEECHAT_CONFIG_OPTION_SET_OK_CHANGED


def config_boolean(option: str) -> int:
    return config_values.get(option) in ["true", "on", "yes", "y", "true", "t", "1"]


def config_integer(option: str) -> int:
    return int(config_values.get(option, 0))


def config_string(option: str) -> str:
    return config_values.get(option, "")


def config_color(option: str) -> str:
    return f"<[config_color:{option}]>"


def color(option: str) -> str:
    return f"<[color:{option}]>"


def info_get(info_name: str, arguments: str):
    if info_name == "color_rgb2term":
        return arguments
    elif info_name == "weechat_data_dir":
        return "."
    else:
        return ""


weechat.config_new_option = config_new_option
weechat.config_option_set = config_option_set
weechat.config_boolean = config_boolean
weechat.config_integer = config_integer
weechat.config_string = config_string
weechat.config_color = config_color
weechat.color = color
weechat.info_get = info_get

shared.weechat_version = 0x03080000
shared.weechat_callbacks = {}
shared.standard_emojis = load_standard_emojis()

color_channel_mention = "<[color:<[config_color:channel_mention]>]>"
color_user_mention = "<[color:<[config_color:user_mention]>]>"
color_usergroup_mention = "<[color:<[config_color:usergroup_mention]>]>"
color_reset = "<[color:reset]>"

workspace_id = "T0FC8BFQR"

with open("mock_data/slack_users_info_person.json") as f:
    user_test1_info_response: SlackUserInfoSuccessResponse[SlackUserInfo] = json.loads(
        f.read()
    )
    user_test1_info = user_test1_info_response["user"]
    user_test1_id = user_test1_info["id"]

with open("mock_data/slack_conversations_info_channel_public.json") as f:
    channel_public_info_response: SlackConversationsInfoSuccessResponse[
        SlackConversationsInfo
    ] = json.loads(f.read())
    channel_public_info = channel_public_info_response["channel"]
    channel_public_id = channel_public_info["id"]


@pytest.fixture
def workspace():
    shared.config = SlackConfig()
    w = SlackWorkspace("workspace_name")
    w.id = workspace_id

    user_test1 = SlackUser(w, user_test1_info)
    user_test1_future = Future[SlackUser]()
    user_test1_future.set_result(user_test1)
    w.my_user = user_test1
    w.users[user_test1_id] = user_test1_future

    channel_public = SlackConversation(w, channel_public_info)
    channel_public_future = Future[SlackConversation]()
    channel_public_future.set_result(channel_public)
    w.conversations[channel_public_id] = channel_public_future

    return w


@pytest.fixture
def channel_public(workspace: SlackWorkspace):
    return workspace.conversations[channel_public_id].result()


@pytest.fixture
def message1_in_channel_public(channel_public: SlackConversation):
    with open("mock_data/slack_conversations_history_channel_public.json") as f:
        history_response: SlackConversationsHistorySuccessResponse = json.loads(
            f.read()
        )
        return SlackMessage(channel_public, history_response["messages"][0])


def resolve_pending_message_item(item: Union[str, PendingMessageItem]) -> str:
    if isinstance(item, str):
        return item

    coroutine = item.resolve()

    with pytest.raises(StopIteration) as excinfo:
        coroutine.send(None)
    return excinfo.value.value

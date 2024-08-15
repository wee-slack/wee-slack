from __future__ import annotations

import re
from itertools import chain

import weechat

from slack.commands import find_command
from slack.python_compatibility import removeprefix, removesuffix
from slack.shared import MESSAGE_ID_REGEX_STRING, REACTION_CHANGE_REGEX_STRING, shared
from slack.slack_conversation import SlackConversation
from slack.slack_message_buffer import SlackMessageBuffer
from slack.slack_user import get_user_nick, name_from_user_info
from slack.task import run_async
from slack.util import get_callback_name, get_resolved_futures

REACTION_PREFIX_REGEX_STRING = (
    rf"{MESSAGE_ID_REGEX_STRING}?{REACTION_CHANGE_REGEX_STRING}"
)


def completion_slack_workspaces_cb(
    data: str, completion_item: str, buffer: str, completion: str
) -> int:
    for workspace_name in shared.workspaces:
        weechat.completion_list_add(
            completion, workspace_name, 0, weechat.WEECHAT_LIST_POS_SORT
        )
    return weechat.WEECHAT_RC_OK


def completion_list_add_expand(
    completion: str, word: str, nick_completion: int, where: str, buffer: str
):
    if word == "%(slack_workspaces)":
        completion_slack_workspaces_cb("", "slack_workspaces", buffer, completion)
    elif word == "%(nicks)":
        completion_nicks_cb("", "nicks", buffer, completion)
    elif word == "%(threads)":
        completion_thread_hashes_cb("", "threads", buffer, completion)
    else:
        weechat.completion_list_add(completion, word, nick_completion, where)


def completion_slack_workspace_commands_cb(
    data: str, completion_item: str, buffer: str, completion: str
) -> int:
    base_command = weechat.completion_get_string(completion, "base_command")
    base_word = weechat.completion_get_string(completion, "base_word")
    args = weechat.completion_get_string(completion, "args")
    args_without_base_word = removesuffix(args, base_word)

    found_cmd_with_args = find_command(base_command, args_without_base_word)
    if found_cmd_with_args:
        command = found_cmd_with_args[0]
        matching_cmds = [
            removeprefix(cmd, command.cmd).lstrip()
            for cmd in shared.commands
            if cmd.startswith(command.cmd) and cmd != command.cmd
        ]
        if len(matching_cmds) > 1:
            for match in matching_cmds:
                cmd_arg = match.split(" ")
                completion_list_add_expand(
                    completion, cmd_arg[0], 0, weechat.WEECHAT_LIST_POS_SORT, buffer
                )
        else:
            for arg in command.completion.split("|"):
                completion_list_add_expand(
                    completion, arg, 0, weechat.WEECHAT_LIST_POS_SORT, buffer
                )

    return weechat.WEECHAT_RC_OK


def completion_slack_channels_cb(
    data: str, completion_item: str, buffer: str, completion: str
) -> int:
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer is None:
        return weechat.WEECHAT_RC_OK

    conversations = slack_buffer.workspace.open_conversations.values()
    for conversation in conversations:
        if conversation.buffer_type == "channel":
            weechat.completion_list_add(
                completion,
                conversation.name_with_prefix("short_name_without_padding"),
                0,
                weechat.WEECHAT_LIST_POS_SORT,
            )
    return weechat.WEECHAT_RC_OK


def completion_emojis_cb(
    data: str, completion_item: str, buffer: str, completion: str
) -> int:
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer is None:
        return weechat.WEECHAT_RC_OK

    base_word = weechat.completion_get_string(completion, "base_word")
    reaction = re.match(REACTION_PREFIX_REGEX_STRING + ":", base_word)
    prefix = reaction.group(0) if reaction else ":"

    emoji_names = chain(
        shared.standard_emojis.keys(), slack_buffer.workspace.custom_emojis.keys()
    )
    for emoji_name in emoji_names:
        if "::skin-tone-" not in emoji_name:
            weechat.completion_list_add(
                completion,
                f"{prefix}{emoji_name}:",
                0,
                weechat.WEECHAT_LIST_POS_SORT,
            )
    return weechat.WEECHAT_RC_OK


def completion_nicks_cb(
    data: str, completion_item: str, buffer: str, completion: str
) -> int:
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer is None:
        return weechat.WEECHAT_RC_OK

    all_users = get_resolved_futures(slack_buffer.workspace.users.values())
    all_nicks = [user.nick for user in all_users]
    all_raw_nicks = sorted([nick.raw_nick for nick in all_nicks], key=str.casefold)
    for nick in all_raw_nicks:
        weechat.completion_list_add(
            completion,
            f"@{nick}",
            1,
            weechat.WEECHAT_LIST_POS_END,
        )
        weechat.completion_list_add(
            completion,
            nick,
            1,
            weechat.WEECHAT_LIST_POS_END,
        )

    members = (
        slack_buffer.members
        if isinstance(slack_buffer, SlackMessageBuffer)
        else all_nicks
    )

    buffer_nicks = sorted(
        [nick.raw_nick for nick in members], key=str.casefold, reverse=True
    )
    for nick in buffer_nicks:
        weechat.completion_list_add(
            completion,
            nick,
            1,
            weechat.WEECHAT_LIST_POS_BEGINNING,
        )
        weechat.completion_list_add(
            completion,
            f"@{nick}",
            1,
            weechat.WEECHAT_LIST_POS_BEGINNING,
        )

    if isinstance(slack_buffer, SlackMessageBuffer):
        senders = [
            m.sender_user_id
            for m in slack_buffer.messages.values()
            if m.sender_user_id
            and m.subtype in [None, "me_message", "thread_broadcast"]
            and slack_buffer.should_display_message(m)
        ]
        unique_senders = reversed(dict.fromkeys(reversed(senders)))
        sender_users = get_resolved_futures(
            [slack_buffer.workspace.users[sender] for sender in unique_senders]
        )
        nicks = [user.nick.raw_nick for user in sender_users]
        for nick in nicks:
            weechat.completion_list_add(
                completion,
                nick,
                1,
                weechat.WEECHAT_LIST_POS_BEGINNING,
            )
            weechat.completion_list_add(
                completion,
                f"@{nick}",
                1,
                weechat.WEECHAT_LIST_POS_BEGINNING,
            )

    my_user_nick = slack_buffer.workspace.my_user.nick.raw_nick
    weechat.completion_list_add(
        completion,
        f"@{my_user_nick}",
        1,
        weechat.WEECHAT_LIST_POS_END,
    )
    weechat.completion_list_add(
        completion,
        my_user_nick,
        1,
        weechat.WEECHAT_LIST_POS_END,
    )

    return weechat.WEECHAT_RC_OK


def completion_thread_hashes_cb(
    data: str, completion_item: str, buffer: str, completion: str
) -> int:
    slack_buffer = shared.buffers.get(buffer)
    if not isinstance(slack_buffer, SlackConversation):
        return weechat.WEECHAT_RC_OK

    message_tss = sorted(slack_buffer.message_hashes.keys())
    messages = [slack_buffer.messages.get(ts) for ts in message_tss]
    thread_messages = [
        message
        for message in messages
        if message is not None and message.is_thread_parent
    ]
    for message in thread_messages:
        weechat.completion_list_add(
            completion, message.hash, 0, weechat.WEECHAT_LIST_POS_BEGINNING
        )
    for message in thread_messages:
        weechat.completion_list_add(
            completion, f"${message.hash}", 0, weechat.WEECHAT_LIST_POS_BEGINNING
        )
    return weechat.WEECHAT_RC_OK


def complete_input(buffer: str, slack_buffer: SlackMessageBuffer, query: str):
    if (
        slack_buffer.completion_context == "ACTIVE_COMPLETION"
        and slack_buffer.completion_values
    ):
        input_value = weechat.buffer_get_string(buffer, "input")
        input_pos = weechat.buffer_get_integer(buffer, "input_pos")
        result = slack_buffer.completion_values[slack_buffer.completion_index]
        input_before = removesuffix(input_value[:input_pos], query)
        input_after = input_value[input_pos:]
        new_input = input_before + result + input_after
        new_pos = input_pos - len(query) + len(result)

        with slack_buffer.completing():
            weechat.buffer_set(buffer, "input", new_input)
            weechat.buffer_set(buffer, "input_pos", str(new_pos))


def nick_suffix():
    return weechat.config_string(
        weechat.config_get("weechat.completion.nick_completer")
    )


async def complete_user_next(
    buffer: str, slack_buffer: SlackMessageBuffer, query: str, is_first_word: bool
):
    if slack_buffer.completion_context == "NO_COMPLETION":
        slack_buffer.completion_context = "PENDING_COMPLETION"
        search = await slack_buffer.api.edgeapi.fetch_users_search(query)
        if slack_buffer.completion_context != "PENDING_COMPLETION":
            return
        slack_buffer.completion_context = "ACTIVE_COMPLETION"
        suffix = nick_suffix() if is_first_word else " "
        slack_buffer.completion_values = [
            get_user_nick(name_from_user_info(slack_buffer.workspace, user)).raw_nick
            + suffix
            for user in search["results"]
        ]
        slack_buffer.completion_index = 0
    elif slack_buffer.completion_context == "ACTIVE_COMPLETION":
        slack_buffer.completion_index += 1
        if slack_buffer.completion_index >= len(slack_buffer.completion_values):
            slack_buffer.completion_index = 0

    complete_input(buffer, slack_buffer, query)


def complete_previous(buffer: str, slack_buffer: SlackMessageBuffer, query: str) -> int:
    if slack_buffer.completion_context == "ACTIVE_COMPLETION":
        slack_buffer.completion_index -= 1
        if slack_buffer.completion_index < 0:
            slack_buffer.completion_index = len(slack_buffer.completion_values) - 1
        complete_input(buffer, slack_buffer, query)
        return weechat.WEECHAT_RC_OK_EAT
    return weechat.WEECHAT_RC_OK


def input_complete_cb(data: str, buffer: str, command: str) -> int:
    slack_buffer = shared.buffers.get(buffer)
    if isinstance(slack_buffer, SlackMessageBuffer):
        input_value = weechat.buffer_get_string(buffer, "input")
        input_pos = weechat.buffer_get_integer(buffer, "input_pos")
        input_before_cursor = input_value[:input_pos]

        word_index = (
            -2 if slack_buffer.completion_context == "ACTIVE_COMPLETION" else -1
        )
        word_until_cursor = " ".join(input_before_cursor.split(" ")[word_index:])

        if word_until_cursor.startswith("@"):
            query = word_until_cursor[1:]
            is_first_word = word_until_cursor == input_before_cursor

            if command == "/input complete_next":
                run_async(
                    complete_user_next(buffer, slack_buffer, query, is_first_word)
                )
                return weechat.WEECHAT_RC_OK_EAT
            else:
                return complete_previous(buffer, slack_buffer, query)
    return weechat.WEECHAT_RC_OK


def register_completions():
    if shared.weechat_version < 0x02090000:
        weechat.completion_get_string = (
            weechat.hook_completion_get_string  # pyright: ignore [reportAttributeAccessIssue, reportUnknownMemberType]
        )
        weechat.completion_list_add = (
            weechat.hook_completion_list_add  # pyright: ignore [reportAttributeAccessIssue, reportUnknownMemberType]
        )

    # Disable until working properly
    # weechat.hook_command_run(
    #     "/input complete_*", get_callback_name(input_complete_cb), ""
    # )

    weechat.hook_completion(
        "slack_workspaces",
        "Slack workspaces (internal names)",
        get_callback_name(completion_slack_workspaces_cb),
        "",
    )
    weechat.hook_completion(
        "slack_commands",
        "completions for Slack commands",
        get_callback_name(completion_slack_workspace_commands_cb),
        "",
    )
    weechat.hook_completion(
        "slack_channels",
        "conversations in the current Slack workspace",
        get_callback_name(completion_slack_channels_cb),
        "",
    )
    weechat.hook_completion(
        "slack_emojis",
        "Emoji names known to Slack",
        get_callback_name(completion_emojis_cb),
        "",
    )
    weechat.hook_completion(
        "nicks",
        "nicks in the current Slack buffer",
        get_callback_name(completion_nicks_cb),
        "",
    )
    weechat.hook_completion(
        "threads",
        "complete thread ids for slack",
        get_callback_name(completion_thread_hashes_cb),
        "",
    )

from __future__ import annotations

import json
import locale
import pprint
import re
from dataclasses import dataclass
from functools import wraps
from itertools import chain
from typing import Callable, Dict, List, Optional, Tuple

import weechat

from slack.error import SlackError, SlackRtmError, UncaughtError
from slack.log import open_debug_buffer, print_error
from slack.python_compatibility import format_exception, removeprefix, removesuffix
from slack.shared import MESSAGE_ID_REGEX_STRING, REACTION_CHANGE_REGEX_STRING, shared
from slack.slack_buffer import SlackBuffer
from slack.slack_conversation import SlackConversation
from slack.slack_thread import SlackThread
from slack.slack_user import name_from_user_info_without_spaces
from slack.slack_workspace import SlackWorkspace
from slack.task import run_async, sleep
from slack.util import get_callback_name, with_color
from slack.weechat_config import WeeChatOption, WeeChatOptionTypes

REACTION_PREFIX_REGEX_STRING = (
    rf"{MESSAGE_ID_REGEX_STRING}?{REACTION_CHANGE_REGEX_STRING}"
)

commands: Dict[str, Command] = {}


# def parse_help_docstring(cmd):
#     doc = textwrap.dedent(cmd.__doc__).strip().split("\n", 1)
#     cmd_line = doc[0].split(None, 1)
#     args = "".join(cmd_line[1:])
#     return cmd_line[0], args, doc[1].strip()


def parse_options(args: str):
    regex = re.compile("(?:^| )+-([^ =]+)(?:=([^ ]+))?")
    pos_args = regex.sub("", args)
    options: Dict[str, Optional[str]] = {
        match.group(1): match.group(2) for match in regex.finditer(args)
    }
    return pos_args, options


@dataclass
class Command:
    cmd: str
    top_level: bool
    description: str
    args: str
    args_description: str
    completion: str
    cb: Callable[[str, str], None]


def weechat_command(
    completion: str = "",
    min_args: int = 0,
    split_all_args: bool = False,
    slack_buffer_required: bool = False,
) -> Callable[
    [Callable[[str, List[str], Dict[str, Optional[str]]], None]],
    Callable[[str, str], None],
]:
    def decorator(
        f: Callable[[str, List[str], Dict[str, Optional[str]]], None]
    ) -> Callable[[str, str], None]:
        cmd = removeprefix(f.__name__, "command_").replace("_", " ")
        top_level = " " not in cmd

        @wraps(f)
        def wrapper(buffer: str, args: str):
            pos_args, options = parse_options(args)
            maxsplit = -1 if split_all_args else 0 if min_args == 0 else min_args - 1
            split_args = pos_args.split(" ", maxsplit)
            if min_args and not pos_args or len(split_args) < min_args:
                print_error(
                    f'Too few arguments for command "/{cmd}" (help on command: /help {cmd})'
                )
                return
            return f(buffer, split_args, options)

        commands[cmd] = Command(cmd, top_level, "", "", "", completion, wrapper)

        return wrapper

    return decorator


def list_workspaces(workspace_name: Optional[str] = None, detailed_list: bool = False):
    weechat.prnt("", "")
    weechat.prnt("", "All workspaces:")
    for workspace in shared.workspaces.values():
        display_workspace(workspace, detailed_list)


def display_workspace(workspace: SlackWorkspace, detailed_list: bool):
    if workspace.is_connected:
        weechat.prnt(
            "",
            f" * "
            f"{with_color('chat_server', workspace.name)} "
            f"{with_color('chat_delimiters', '[')}"
            f"connected"
            f"{with_color('chat_delimiters', ']')}"
            f", nick: {workspace.my_user.nick()}"
            f", 0 channel(s), 0 pv",
        )
    else:
        weechat.prnt("", f"   {with_color('chat_server', workspace.name)}")


@weechat_command()
def command_slack(buffer: str, args: List[str], options: Dict[str, Optional[str]]):
    """
    slack command
    """
    print("ran slack")


def workspace_connect(workspace: SlackWorkspace):
    if workspace.is_connected:
        print_error(f'already connected to workspace "{workspace.name}"!')
        return
    elif workspace.is_connecting:
        print_error(f'already connecting to workspace "{workspace.name}"!')
        return
    run_async(workspace.connect())


@weechat_command("%(slack_workspaces)|-all", split_all_args=True)
def command_slack_connect(
    buffer: str, args: List[str], options: Dict[str, Optional[str]]
):
    if options.get("all", False) is None:
        for workspace in shared.workspaces.values():
            run_async(workspace.connect())
    elif args[0]:
        for arg in args:
            workspace = shared.workspaces.get(arg)
            if workspace is None:
                print_error(f'workspace "{arg}" not found')
            else:
                workspace_connect(workspace)
    else:
        slack_buffer = shared.buffers.get(buffer)
        if slack_buffer:
            workspace_connect(slack_buffer.workspace)


def workspace_disconnect(workspace: SlackWorkspace):
    if not workspace.is_connected and not workspace.is_connecting:
        print_error(f'not connected to workspace "{workspace.name}"!')
        return
    workspace.disconnect()


@weechat_command("%(slack_workspaces)|-all", split_all_args=True)
def command_slack_disconnect(
    buffer: str, args: List[str], options: Dict[str, Optional[str]]
):
    if options.get("all", False) is None:
        for workspace in shared.workspaces.values():
            workspace.disconnect()
    elif args[0]:
        for arg in args:
            workspace = shared.workspaces.get(arg)
            if workspace is None:
                print_error(f'workspace "{arg}" not found')
            else:
                workspace_disconnect(workspace)
    else:
        slack_buffer = shared.buffers.get(buffer)
        if slack_buffer:
            workspace_disconnect(slack_buffer.workspace)


@weechat_command()
def command_slack_rehistory(
    buffer: str, args: List[str], options: Dict[str, Optional[str]]
):
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer:
        run_async(slack_buffer.rerender_history())


@weechat_command()
def command_slack_workspace(
    buffer: str, args: List[str], options: Dict[str, Optional[str]]
):
    list_workspaces()


@weechat_command("%(slack_workspaces)")
def command_slack_workspace_list(
    buffer: str, args: List[str], options: Dict[str, Optional[str]]
):
    list_workspaces()


@weechat_command("%(slack_workspaces)")
def command_slack_workspace_listfull(
    buffer: str, args: List[str], options: Dict[str, Optional[str]]
):
    list_workspaces(detailed_list=True)


@weechat_command(min_args=1)
def command_slack_workspace_add(
    buffer: str, args: List[str], options: Dict[str, Optional[str]]
):
    name = args[0]
    if name in shared.workspaces:
        print_error(f'workspace "{name}" already exists, can\'t add it!')
        return

    shared.workspaces[name] = SlackWorkspace(name)

    for option_name, option_value in options.items():
        if hasattr(shared.workspaces[name].config, option_name):
            config_option: WeeChatOption[WeeChatOptionTypes] = getattr(
                shared.workspaces[name].config, option_name
            )
            value = "on" if option_value is None else option_value
            config_option.value_set_as_str(value)

    weechat.prnt(
        "",
        f"{shared.SCRIPT_NAME}: workspace added: {weechat.color('chat_server')}{name}{weechat.color('reset')}",
    )


@weechat_command("%(slack_workspaces)", min_args=2)
def command_slack_workspace_rename(
    buffer: str, args: List[str], options: Dict[str, Optional[str]]
):
    old_name = args[0]
    new_name = args[1]
    workspace = shared.workspaces.get(old_name)
    if not workspace:
        print_error(f'workspace "{old_name}" not found for "workspace rename" command')
        return
    workspace.name = new_name
    shared.workspaces[new_name] = workspace
    del shared.workspaces[old_name]
    weechat.prnt(
        "",
        f"server {with_color('chat_server', old_name)} has been renamed to {with_color('chat_server', new_name)}",
    )
    # TODO: Rename buffers and config


@weechat_command("%(slack_workspaces)", min_args=1)
def command_slack_workspace_del(
    buffer: str, args: List[str], options: Dict[str, Optional[str]]
):
    name = args[0]
    workspace = shared.workspaces.get(name)
    if not workspace:
        print_error(f'workspace "{name}" not found for "workspace del" command')
        return
    if workspace.is_connected:
        print_error(
            f'you can not delete server "{name}" because you are connected to it. Try "/slack disconnect {name}" first.'
        )
        return
    # TODO: Delete config
    del shared.workspaces[name]
    weechat.prnt(
        "",
        f"server {with_color('chat_server', name)} has been deleted",
    )


@weechat_command("%(threads)", min_args=1)
def command_slack_thread(
    buffer: str, args: List[str], options: Dict[str, Optional[str]]
):
    slack_buffer = shared.buffers.get(buffer)
    if isinstance(slack_buffer, SlackConversation):
        run_async(slack_buffer.open_thread(args[0], switch=True))


def print_uncaught_error(
    error: UncaughtError, detailed: bool, options: Dict[str, Optional[str]]
):
    weechat.prnt("", f"  {error.id} ({error.time}): {error.exception}")
    if detailed:
        for line in format_exception(error.exception):
            weechat.prnt("", f"  {line}")
    data = options.get("data", False) is None
    if data:
        if isinstance(error.exception, SlackRtmError):
            weechat.prnt("", f"  data: {json.dumps(error.exception.message_json)}")
        elif isinstance(error.exception, SlackError):
            weechat.prnt("", f"  data: {json.dumps(error.exception.data)}")
        else:
            print_error("This error does not have any data")


@weechat_command("tasks|buffer|open_buffer|errors|error", split_all_args=True)
def command_slack_debug(
    buffer: str, args: List[str], options: Dict[str, Optional[str]]
):
    # TODO: Add message info (message_json)
    if args[0] == "tasks":
        weechat.prnt("", "Active tasks:")
        weechat.prnt("", pprint.pformat(shared.active_tasks))
        weechat.prnt("", "Active futures:")
        weechat.prnt("", pprint.pformat(shared.active_futures))
    elif args[0] == "buffer":
        slack_buffer = shared.buffers.get(buffer)
        if isinstance(slack_buffer, SlackConversation):
            weechat.prnt("", f"Conversation id: {slack_buffer.id}")
        elif isinstance(slack_buffer, SlackThread):
            weechat.prnt(
                "",
                f"Conversation id: {slack_buffer.parent.conversation.id}, Thread ts: {slack_buffer.parent.thread_ts}, Thread hash: {slack_buffer.parent.hash}",
            )
    elif args[0] == "open_buffer":
        open_debug_buffer()
    elif args[0] == "errors":
        num_arg = int(args[1]) if len(args) > 1 and args[1].isdecimal() else 5
        num = min(num_arg, len(shared.uncaught_errors))
        weechat.prnt("", f"Last {num} errors:")
        for error in shared.uncaught_errors[-num:]:
            print_uncaught_error(error, False, options)
    elif args[0] == "error":
        if len(args) > 1:
            if args[1].isdecimal() and args[1] != "0":
                num = int(args[1])
                if num > len(shared.uncaught_errors):
                    print_error(
                        f"Only {len(shared.uncaught_errors)} error(s) have occurred"
                    )
                    return
                error = shared.uncaught_errors[-num]
            else:
                errors = [e for e in shared.uncaught_errors if e.id == args[1]]
                if not errors:
                    print_error(f"Error {args[1]} not found")
                    return
                error = errors[0]
            weechat.prnt("", f"Error {error.id}:")
        elif not shared.uncaught_errors:
            weechat.prnt("", "No errors have occurred")
            return
        else:
            error = shared.uncaught_errors[-1]
            weechat.prnt("", "Last error:")
        print_uncaught_error(error, True, options)


def completion_slack_workspaces_cb(
    data: str, completion_item: str, buffer: str, completion: str
) -> int:
    for workspace_name in shared.workspaces:
        weechat.completion_list_add(
            completion, workspace_name, 0, weechat.WEECHAT_LIST_POS_SORT
        )
    return weechat.WEECHAT_RC_OK


def find_command(start_cmd: str, args: str) -> Optional[Tuple[Command, str]]:
    args_parts = re.finditer("[^ ]+", args)
    cmd = start_cmd
    cmd_args_startpos = 0

    for part in args_parts:
        next_cmd = f"{cmd} {part.group(0)}"
        if next_cmd not in commands:
            cmd_args_startpos = part.start(0)
            break
        cmd = next_cmd
    else:
        cmd_args_startpos = len(args)

    cmd_args = args[cmd_args_startpos:]
    if cmd in commands:
        return commands[cmd], cmd_args
    return None


def command_cb(data: str, buffer: str, args: str) -> int:
    found_cmd_with_args = find_command(data, args)
    if found_cmd_with_args:
        command = found_cmd_with_args[0]
        cmd_args = found_cmd_with_args[1]
        command.cb(buffer, cmd_args)
    else:
        print_error(
            f'Error with command "/{data} {args}" (help on command: /help {data})'
        )

    return weechat.WEECHAT_RC_OK


def completion_list_add_expand(
    completion: str, word: str, nick_completion: int, where: str, buffer: str
):
    if word == "%(slack_workspaces)":
        completion_slack_workspaces_cb("", "slack_workspaces", buffer, completion)
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
            for cmd in commands
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


def completion_nicks_cb(
    data: str, completion_item: str, buffer: str, completion: str
) -> int:
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer is None:
        return weechat.WEECHAT_RC_OK

    buffer_nicks = set(f"@{user.nick(only_nick=True)}" for user in slack_buffer.members)
    for nick in sorted(buffer_nicks, key=locale.strxfrm):
        weechat.completion_list_add(
            completion,
            nick,
            1,
            weechat.WEECHAT_LIST_POS_END,
        )

    workspace_nicks = set(
        f"@{user.result().nick(only_nick=True)}"
        for user in slack_buffer.workspace.users.values()
        if user.done_with_result()
    )
    for nick in sorted(workspace_nicks - buffer_nicks, key=locale.strxfrm):
        weechat.completion_list_add(
            completion,
            nick,
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


def complete_input(slack_buffer: SlackBuffer, query: str):
    if (
        slack_buffer.completion_context == "ACTIVE_COMPLETION"
        and slack_buffer.completion_values
    ):
        input_value = weechat.buffer_get_string(slack_buffer.buffer_pointer, "input")
        input_pos = weechat.buffer_get_integer(slack_buffer.buffer_pointer, "input_pos")
        result = slack_buffer.completion_values[slack_buffer.completion_index]
        input_before = removesuffix(input_value[:input_pos], query)
        input_after = input_value[input_pos:]
        new_input = input_before + result + input_after
        new_pos = input_pos - len(query) + len(result)

        with slack_buffer.completing():
            weechat.buffer_set(slack_buffer.buffer_pointer, "input", new_input)
            weechat.buffer_set(slack_buffer.buffer_pointer, "input_pos", str(new_pos))


def nick_suffix():
    return weechat.config_string(
        weechat.config_get("weechat.completion.nick_completer")
    )


async def complete_user_next(
    slack_buffer: SlackBuffer, query: str, is_first_word: bool
):
    if slack_buffer.completion_context == "NO_COMPLETION":
        slack_buffer.completion_context = "PENDING_COMPLETION"
        search = await slack_buffer.workspace.api.edgeapi.fetch_users_search(query)
        if slack_buffer.completion_context != "PENDING_COMPLETION":
            return
        slack_buffer.completion_context = "ACTIVE_COMPLETION"
        suffix = nick_suffix() if is_first_word else " "
        slack_buffer.completion_values = [
            name_from_user_info_without_spaces(slack_buffer.workspace, user) + suffix
            for user in search["results"]
        ]
        slack_buffer.completion_index = 0
    elif slack_buffer.completion_context == "ACTIVE_COMPLETION":
        slack_buffer.completion_index += 1
        if slack_buffer.completion_index >= len(slack_buffer.completion_values):
            slack_buffer.completion_index = 0

    complete_input(slack_buffer, query)


def complete_previous(slack_buffer: SlackBuffer, query: str) -> int:
    if slack_buffer.completion_context == "ACTIVE_COMPLETION":
        slack_buffer.completion_index -= 1
        if slack_buffer.completion_index < 0:
            slack_buffer.completion_index = len(slack_buffer.completion_values) - 1
        complete_input(slack_buffer, query)
        return weechat.WEECHAT_RC_OK_EAT
    return weechat.WEECHAT_RC_OK


async def mark_read(slack_buffer: SlackBuffer):
    # Sleep so the read marker is updated before we run slack_buffer.mark_read
    await sleep(1)
    await slack_buffer.mark_read()


def buffer_set_unread_cb(data: str, buffer: str, command: str) -> int:
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer:
        run_async(mark_read(slack_buffer))
    return weechat.WEECHAT_RC_OK


def input_complete_cb(data: str, buffer: str, command: str) -> int:
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer:
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
                run_async(complete_user_next(slack_buffer, query, is_first_word))
                return weechat.WEECHAT_RC_OK_EAT
            else:
                return complete_previous(slack_buffer, query)
    return weechat.WEECHAT_RC_OK


def register_commands():
    if shared.weechat_version < 0x02090000:
        weechat.completion_get_string = (
            weechat.hook_completion_get_string  # pyright: ignore [reportUnknownMemberType, reportGeneralTypeIssues]
        )
        weechat.completion_list_add = (
            weechat.hook_completion_list_add  # pyright: ignore [reportUnknownMemberType, reportGeneralTypeIssues]
        )

    weechat.hook_command_run(
        "/buffer set unread", get_callback_name(buffer_set_unread_cb), ""
    )
    weechat.hook_command_run(
        "/buffer set unread *", get_callback_name(buffer_set_unread_cb), ""
    )
    weechat.hook_command_run(
        "/input set_unread_current_buffer", get_callback_name(buffer_set_unread_cb), ""
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

    for cmd, command in commands.items():
        if command.top_level:
            weechat.hook_command(
                command.cmd,
                command.description,
                command.args,
                command.args_description,
                "%(slack_commands)|%*",
                get_callback_name(command_cb),
                cmd,
            )

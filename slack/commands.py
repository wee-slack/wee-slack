from __future__ import annotations

import re
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple

import weechat

from slack.api import SlackWorkspace
from slack.log import print_error
from slack.shared import shared
from slack.task import create_task
from slack.util import get_callback_name, with_color
from slack.weechat_config import WeeChatOption

commands: Dict[str, Command] = {}


# def parse_help_docstring(cmd):
#     doc = textwrap.dedent(cmd.__doc__).strip().split("\n", 1)
#     cmd_line = doc[0].split(None, 1)
#     args = "".join(cmd_line[1:])
#     return cmd_line[0], args, doc[1].strip()


def parse_options(args: str):
    regex = re.compile(" +-([^ =]+)(?:=([^ ]+))?")
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
    completion: str = "", min_args: int = 0, slack_buffer_required: bool = False
):
    def decorator(f: Callable[[str, List[str], Dict[str, Optional[str]]], None]):
        cmd = f.__name__.removeprefix("command_").replace("_", " ")
        top_level = " " not in cmd

        @wraps(f)
        def wrapper(buffer: str, args: str):
            pos_args, options = parse_options(args)
            split_args = pos_args.split(" ", min_args)
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
            f", nick: {workspace.nick}"
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


@weechat_command("%(slack_workspaces)")
def command_slack_connect(
    buffer: str, args: List[str], options: Dict[str, Optional[str]]
):
    async def connect():
        if args and args[0]:
            workspace = shared.workspaces.get(args[0])
            if workspace:
                await workspace.connect()
            else:
                print_error(f'workspace "{args[0]}" not found')
        else:
            for workspace in shared.workspaces.values():
                await workspace.connect()

    create_task(connect())


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
            config_option: WeeChatOption[Any] = getattr(
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


def completion_list_add(completion: str, word: str, nick_completion: int, where: str):
    if word == "%(slack_workspaces)":
        completion_slack_workspaces_cb("", "slack_workspaces", "", completion)
    else:
        weechat.completion_list_add(completion, word, nick_completion, where)


def completion_slack_workspace_commands_cb(
    data: str, completion_item: str, buffer: str, completion: str
) -> int:
    base_command = weechat.completion_get_string(completion, "base_command")
    base_word = weechat.completion_get_string(completion, "base_word")
    args = weechat.completion_get_string(completion, "args")
    args_without_base_word = args.removesuffix(base_word)

    found_cmd_with_args = find_command(base_command, args_without_base_word)
    if found_cmd_with_args:
        command = found_cmd_with_args[0]
        matching_cmds = [
            cmd.removeprefix(command.cmd).lstrip()
            for cmd in commands
            if cmd.startswith(command.cmd) and cmd != command.cmd
        ]
        if len(matching_cmds) > 1:
            for match in matching_cmds:
                cmd_arg = match.split(" ")
                completion_list_add(
                    completion, cmd_arg[0], 0, weechat.WEECHAT_LIST_POS_SORT
                )
        else:
            for arg in command.completion.split("|"):
                completion_list_add(completion, arg, 0, weechat.WEECHAT_LIST_POS_SORT)

    return weechat.WEECHAT_RC_OK


def completion_irc_channels_cb(
    data: str, completion_item: str, buffer: str, completion: str
) -> int:
    if weechat.buffer_get_string(buffer, "full_name").startswith("core."):
        weechat.completion_list_add(
            completion, "#asd", 0, weechat.WEECHAT_LIST_POS_SORT
        )
    return weechat.WEECHAT_RC_OK


def register_commands():
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
        "irc_channels",
        "channels on all Slack workspaces",
        get_callback_name(completion_irc_channels_cb),
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

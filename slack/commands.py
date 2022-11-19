from __future__ import annotations

import re
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

import weechat

from slack.api import SlackWorkspace
from slack.config import WeeChatOption
from slack.log import print_error
from slack.shared import shared
from slack.util import get_callback_name, with_color

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


def weechat_command(min_args: int = 0, slack_buffer_required: bool = False):
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

        commands[cmd] = Command(cmd, top_level, "", "", "", "", wrapper)

        return wrapper

    return decorator


def list_workspaces(workspace_name: Optional[str] = None, detailed_list: bool = False):
    weechat.prnt("", "")
    weechat.prnt("", "All workspaces:")
    for workspace in shared.workspaces.values():
        display_workspace(workspace, detailed_list)


def display_workspace(workspace: SlackWorkspace, detailed_list: bool):
    if workspace.connected:
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


@weechat_command()
def command_slack_workspace(
    buffer: str, args: List[str], options: Dict[str, Optional[str]]
):
    list_workspaces()


@weechat_command()
def command_slack_workspace_list(
    buffer: str, args: List[str], options: Dict[str, Optional[str]]
):
    list_workspaces()


@weechat_command()
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


def command_cb(data: str, buffer: str, args: str) -> int:
    args_parts = re.finditer("[^ ]+", args)
    cmd = data
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
        commands[cmd].cb(buffer, cmd_args)
    else:
        print_error(
            f'Error with command "/{data} {args}" (help on command: /help {data})'
        )

    return weechat.WEECHAT_RC_OK


def register_commands():
    for cmd, command in commands.items():
        if command.top_level:
            weechat.hook_command(
                command.cmd,
                command.description,
                command.args,
                command.args_description,
                command.completion,
                get_callback_name(command_cb),
                cmd,
            )

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import wraps
from typing import Callable, Dict, List

import weechat

from slack.api import SlackWorkspace
from slack.log import print_error
from slack.shared import shared
from slack.util import get_callback_name

commands: Dict[str, Command] = {}


# def parse_help_docstring(cmd):
#     doc = textwrap.dedent(cmd.__doc__).strip().split("\n", 1)
#     cmd_line = doc[0].split(None, 1)
#     args = "".join(cmd_line[1:])
#     return cmd_line[0], args, doc[1].strip()


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
    def decorator(f: Callable[[str, List[str]], None]):
        cmd = f.__name__.removeprefix("command_").replace("_", " ")
        top_level = " " not in cmd

        @wraps(f)
        def wrapper(buffer: str, args: str):
            split_args = args.split(" ", min_args)
            if min_args and not args or len(split_args) < min_args:
                print_error(
                    f'Too few arguments for command "/{cmd}" (help on command: /help {cmd})'
                )
                return
            return f(buffer, split_args)

        commands[cmd] = Command(cmd, top_level, "", "", "", "", wrapper)

        return wrapper

    return decorator


@weechat_command()
def command_slack(buffer: str, args: List[str]):
    """
    slack command
    """
    print("ran slack")


@weechat_command()
def command_slack_workspace(buffer: str, args: List[str]):
    print("ran workspace")


@weechat_command(min_args=1)
def command_slack_workspace_add(buffer: str, args: List[str]):
    name = args[0]
    if name in shared.workspaces:
        print_error(f'workspace "{name}" already exists, can\'t add it!')
        return
    shared.workspaces[name] = SlackWorkspace(name)
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

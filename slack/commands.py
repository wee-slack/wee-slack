from __future__ import annotations

import json
import pprint
import re
from dataclasses import dataclass
from functools import wraps
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

import weechat

from slack.error import SlackError, SlackRtmError, UncaughtError
from slack.log import open_debug_buffer, print_error
from slack.python_compatibility import format_exception, removeprefix
from slack.shared import shared
from slack.slack_buffer import SlackBuffer
from slack.slack_conversation import SlackConversation
from slack.slack_thread import SlackThread
from slack.slack_user import SlackUser
from slack.slack_workspace import SlackWorkspace
from slack.task import gather, run_async, sleep
from slack.util import get_callback_name, get_resolved_futures, with_color
from slack.weechat_config import WeeChatOption, WeeChatOptionTypes

if TYPE_CHECKING:
    from typing_extensions import Literal

    Options = Dict[str, Union[str, Literal[True]]]
    WeechatCommandCallback = Callable[[str, str], None]
    InternalCommandCallback = Callable[
        [str, List[str], Options], Optional[Coroutine[Any, None, None]]
    ]

T = TypeVar("T")


# def parse_help_docstring(cmd):
#     doc = textwrap.dedent(cmd.__doc__).strip().split("\n", 1)
#     cmd_line = doc[0].split(None, 1)
#     args = "".join(cmd_line[1:])
#     return cmd_line[0], args, doc[1].strip()


def parse_options(args: str):
    regex = re.compile("(?:^| )+-([^ =]+)(?:=([^ ]+))?")
    pos_args = regex.sub("", args)
    options: Options = {
        match.group(1): match.group(2) or True for match in regex.finditer(args)
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
    cb: WeechatCommandCallback


def weechat_command(
    completion: str = "",
    min_args: int = 0,
    split_all_args: bool = False,
    slack_buffer_required: bool = False,
) -> Callable[
    [InternalCommandCallback],
    WeechatCommandCallback,
]:
    def decorator(
        f: InternalCommandCallback,
    ) -> WeechatCommandCallback:
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
            result = f(buffer, split_args, options)
            if result is not None:
                run_async(result)
            return

        shared.commands[cmd] = Command(cmd, top_level, "", "", "", completion, wrapper)

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
            f", nick: {workspace.my_user.nick.format()}"
            f", 0 channel(s), 0 pv",
        )
    else:
        weechat.prnt("", f"   {with_color('chat_server', workspace.name)}")


@weechat_command()
def command_slack(buffer: str, args: List[str], options: Options):
    """
    slack command
    """
    print("ran slack")


async def workspace_connect(workspace: SlackWorkspace):
    if workspace.is_connected:
        print_error(f'already connected to workspace "{workspace.name}"!')
        return
    elif workspace.is_connecting:
        print_error(f'already connecting to workspace "{workspace.name}"!')
        return
    await workspace.connect()


@weechat_command("%(slack_workspaces)|-all", split_all_args=True)
async def command_slack_connect(buffer: str, args: List[str], options: Options):
    if options.get("all"):
        for workspace in shared.workspaces.values():
            await workspace.connect()
    elif args[0]:
        for arg in args:
            workspace = shared.workspaces.get(arg)
            if workspace is None:
                print_error(f'workspace "{arg}" not found')
            else:
                await workspace_connect(workspace)
    else:
        slack_buffer = shared.buffers.get(buffer)
        if slack_buffer:
            await workspace_connect(slack_buffer.workspace)


def workspace_disconnect(workspace: SlackWorkspace):
    if not workspace.is_connected and not workspace.is_connecting:
        print_error(f'not connected to workspace "{workspace.name}"!')
        return
    workspace.disconnect()


@weechat_command("%(slack_workspaces)|-all", split_all_args=True)
def command_slack_disconnect(buffer: str, args: List[str], options: Options):
    if options.get("all"):
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
async def command_slack_rehistory(buffer: str, args: List[str], options: Options):
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer:
        await slack_buffer.rerender_history()


@weechat_command()
def command_slack_workspace(buffer: str, args: List[str], options: Options):
    list_workspaces()


@weechat_command("%(slack_workspaces)")
def command_slack_workspace_list(buffer: str, args: List[str], options: Options):
    list_workspaces()


@weechat_command("%(slack_workspaces)")
def command_slack_workspace_listfull(buffer: str, args: List[str], options: Options):
    list_workspaces(detailed_list=True)


@weechat_command(min_args=1)
def command_slack_workspace_add(buffer: str, args: List[str], options: Options):
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
            value = "on" if option_value is True else option_value
            config_option.value_set_as_str(value)

    weechat.prnt(
        "",
        f"{shared.SCRIPT_NAME}: workspace added: {weechat.color('chat_server')}{name}{weechat.color('reset')}",
    )


@weechat_command("%(slack_workspaces)", min_args=2)
def command_slack_workspace_rename(buffer: str, args: List[str], options: Options):
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
def command_slack_workspace_del(buffer: str, args: List[str], options: Options):
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


async def create_conversation_for_users(
    workspace: SlackWorkspace, users: Iterable[SlackUser]
):
    user_ids = [user.id for user in users]
    conversation_open_response = await workspace.api.conversations_open(user_ids)
    conversation_id = conversation_open_response["channel"]["id"]
    workspace.conversations.initialize_items(
        [conversation_id], {conversation_id: conversation_open_response["channel"]}
    )
    conversation = await workspace.conversations[conversation_id]
    await conversation.open_buffer(switch=True)


@weechat_command("%(nicks)", min_args=1, split_all_args=True)
async def command_slack_query(buffer: str, args: List[str], options: Options):
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer is None:
        return

    nicks = [removeprefix(nick, "@") for nick in args]
    all_users = get_resolved_futures(slack_buffer.workspace.users.values())
    users = [user for user in all_users if user.nick.raw_nick in nicks]

    if len(users) != len(nicks):
        found_nicks = [user.nick.raw_nick for user in users]
        not_found_nicks = [nick for nick in nicks if nick not in found_nicks]
        print_error(
            f"No such nick{'s' if len(not_found_nicks) > 1 else ''}: {', '.join(not_found_nicks)}"
        )
        return

    if len(users) == 1:
        user = users[0]
        all_conversations = get_resolved_futures(
            slack_buffer.workspace.conversations.values()
        )
        for conversation in all_conversations:
            if conversation.im_user_id == user.id:
                await conversation.open_buffer(switch=True)
                return

    await create_conversation_for_users(slack_buffer.workspace, users)


def get_conversation_from_args(buffer: str, args: List[str], options: Options):
    slack_buffer = shared.buffers.get(buffer)

    workspace_name = options.get("workspace")
    if workspace_name is True:
        print_error("No workspace specified")
        return

    workspace = (
        shared.workspaces.get(workspace_name)
        if workspace_name
        else slack_buffer.workspace
        if slack_buffer is not None
        else None
    )

    if workspace is None:
        if workspace_name:
            print_error(f'Workspace "{workspace_name}" not found')
        else:
            print_error(
                "Must be run from a slack buffer unless a workspace is specified"
            )
        return

    if len(args) == 0 or not args[0]:
        if workspace_name is not None:
            print_error(
                "Must specify conversaton name when workspace name is specified"
            )
            return
        if isinstance(slack_buffer, SlackConversation):
            return slack_buffer
        else:
            return

    conversation_name = args[0].strip()
    all_conversations = get_resolved_futures(workspace.conversations.values())
    for conversation in all_conversations:
        if (
            conversation.name_with_prefix("short_name_without_padding")
            == conversation_name
            or conversation.name() == conversation_name
        ):
            return conversation

    print_error(f'Conversation "{conversation_name}" not found')


@weechat_command("")
async def command_slack_join(buffer: str, args: List[str], options: Options):
    conversation = get_conversation_from_args(buffer, args, options)
    if conversation is not None:
        await conversation.workspace.api.conversations_join(conversation.id)
        await conversation.open_buffer(switch=not options.get("noswitch"))


@weechat_command("")
async def command_slack_part(buffer: str, args: List[str], options: Options):
    conversation = get_conversation_from_args(buffer, args, options)
    if conversation is not None:
        await conversation.part()


@weechat_command("%(threads)", min_args=1)
async def command_slack_thread(buffer: str, args: List[str], options: Options):
    slack_buffer = shared.buffers.get(buffer)
    if isinstance(slack_buffer, SlackConversation):
        await slack_buffer.open_thread(args[0], switch=True)


@weechat_command("-alsochannel|%(threads)", min_args=1)
async def command_slack_reply(buffer: str, args: List[str], options: Options):
    slack_buffer = shared.buffers.get(buffer)
    broadcast = bool(options.get("alsochannel"))
    if isinstance(slack_buffer, SlackThread):
        await slack_buffer.post_message(args[0], broadcast=broadcast)
    elif isinstance(slack_buffer, SlackConversation):
        split_args = args[0].split(" ", 1)
        if len(split_args) < 2:
            print_error(
                'Too few arguments for command "/slack reply" (help on command: /help slack reply)'
            )
            return
        thread_ts = slack_buffer.ts_from_hash_or_index(split_args[0])
        await slack_buffer.post_message(split_args[1], thread_ts, broadcast)


@weechat_command("away|active")
async def command_slack_presence(buffer: str, args: List[str], options: Options):
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer is None:
        return
    new_presence = args[0]
    if new_presence not in ("active", "away"):
        print_error(
            f'Error with command "/slack presence {args[0]}" (help on command: /help slack presence)'
        )
        return
    await slack_buffer.workspace.api.set_presence(new_presence)


@weechat_command("list")
async def command_slack_mute(buffer: str, args: List[str], options: Options):
    slack_buffer = shared.buffers.get(buffer)
    if not isinstance(slack_buffer, SlackConversation):
        return

    if args[0] == "list":
        conversations = await gather(
            *[
                slack_buffer.workspace.conversations[conversation_id]
                for conversation_id in slack_buffer.workspace.muted_channels
            ]
        )
        conversation_names = sorted(
            conversation.name_with_prefix("short_name_without_padding")
            for conversation in conversations
        )
        weechat.prnt("", f"Muted conversations: {', '.join(conversation_names)}")
        return

    muted_channels = set(slack_buffer.workspace.muted_channels)
    muted_channels ^= {slack_buffer.id}
    await slack_buffer.workspace.api.set_muted_channels(muted_channels)
    muted_str = "Muted" if slack_buffer.id in muted_channels else "Unmuted"
    weechat.prnt(
        "",
        f"{muted_str} channel {slack_buffer.name_with_prefix('short_name_without_padding')}",
    )


def print_uncaught_error(error: UncaughtError, detailed: bool, options: Options):
    weechat.prnt("", f"  {error.id} ({error.time}): {error.exception}")
    if detailed:
        for line in format_exception(error.exception):
            weechat.prnt("", f"  {line}")
    if options.get("data"):
        if isinstance(error.exception, SlackRtmError):
            weechat.prnt("", f"  data: {json.dumps(error.exception.message_json)}")
        elif isinstance(error.exception, SlackError):
            weechat.prnt("", f"  data: {json.dumps(error.exception.data)}")
        else:
            print_error("This error does not have any data")


@weechat_command("tasks|buffer|open_buffer|errors|error", split_all_args=True)
def command_slack_debug(buffer: str, args: List[str], options: Options):
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


@weechat_command("-clear")
async def command_slack_status(buffer: str, args: List[str], options: Options):
    status = args[0]
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer is not None:
        if options.get("clear"):
            await slack_buffer.workspace.api.clear_user_status()
        elif slack_buffer and len(status) > 0:
            await slack_buffer.workspace.api.set_user_status(status)
        else:
            print_error(
                'Too few arguments for command "/slack status" (help on command: /help slack status)'
            )
    else:
        print_error("Run the command in a slack buffer")


def find_command(start_cmd: str, args: str) -> Optional[Tuple[Command, str]]:
    args_parts = re.finditer("[^ ]+", args)
    cmd = start_cmd
    cmd_args_startpos = 0

    for part in args_parts:
        next_cmd = f"{cmd} {part.group(0)}"
        if next_cmd not in shared.commands:
            cmd_args_startpos = part.start(0)
            break
        cmd = next_cmd
    else:
        cmd_args_startpos = len(args)

    cmd_args = args[cmd_args_startpos:]
    if cmd in shared.commands:
        return shared.commands[cmd], cmd_args
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


async def mark_read(slack_buffer: SlackBuffer):
    # Sleep so the read marker is updated before we run slack_buffer.mark_read
    await sleep(1)
    await slack_buffer.mark_read()


def buffer_set_unread_cb(data: str, buffer: str, command: str) -> int:
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer:
        run_async(mark_read(slack_buffer))
    return weechat.WEECHAT_RC_OK


def register_commands():
    weechat.hook_command_run(
        "/buffer set unread", get_callback_name(buffer_set_unread_cb), ""
    )
    weechat.hook_command_run(
        "/buffer set unread *", get_callback_name(buffer_set_unread_cb), ""
    )
    weechat.hook_command_run(
        "/input set_unread_current_buffer", get_callback_name(buffer_set_unread_cb), ""
    )

    for cmd, command in shared.commands.items():
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

from __future__ import annotations

import ast
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
from slack.shared import EMOJI_CHAR_OR_NAME_REGEX_STRING, shared
from slack.slack_buffer import SlackBuffer
from slack.slack_conversation import SlackConversation, create_conversation_for_users
from slack.slack_message import SlackTs, ts_from_tag
from slack.slack_message_buffer import SlackMessageBuffer
from slack.slack_search_buffer import SlackSearchBuffer
from slack.slack_thread import SlackThread
from slack.slack_workspace import SlackWorkspace
from slack.task import gather, run_async, sleep
from slack.util import get_callback_name, get_resolved_futures, with_color
from slack.weechat_config import WeeChatOption, WeeChatOptionTypes

if TYPE_CHECKING:
    from typing_extensions import Literal, assert_never

    Options = Dict[str, Union[str, Literal[True]]]
    WeechatCommandCallback = Callable[[str, str], None]
    InternalCommandCallback = Callable[
        [str, List[str], Options], Optional[Coroutine[Any, None, None]]
    ]

T = TypeVar("T")

focus_events = ("auto", "message", "delete", "linkarchive", "reply", "thread")


def print_message_not_found_error(msg_id: str):
    if msg_id:
        print_error(
            "Invalid id given, must be an existing id or a number greater "
            + "than 0 and less than the number of messages in the channel"
        )
    else:
        print_error("No messages found in channel")


# def parse_help_docstring(cmd):
#     doc = textwrap.dedent(cmd.__doc__).strip().split("\n", maxsplit=1)
#     cmd_line = doc[0].split(None, maxsplit=1)
#     args = "".join(cmd_line[1:])
#     return cmd_line[0], args, doc[1].strip()


def parse_options(args: str, options_only_first: bool):
    regex = re.compile("(?:^| )+(-([^ =]+)(?:=([^ ]+))?|[^ ]+)")
    options: Options = {}
    for match in regex.finditer(args):
        if match.group(2) is not None:
            options[match.group(2)] = match.group(3) or True
        elif options_only_first:
            break
    sub_count = len(options) if options_only_first else 0
    pos_args = (
        regex.sub(
            lambda m: m.group(0) if m.group(2) is None else "", args, count=sub_count
        ).strip()
        if options
        else args
    )
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
    alias: Optional[str]


def weechat_command(
    completion: str = "",
    min_args: int = 0,
    max_split: Optional[int] = None,
    slack_buffer_required: bool = False,
    alias: Optional[str] = None,
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
            re_maxsplit = (
                max_split
                if max_split is not None
                else -1
                if min_args == 1
                else min_args - 1
            )
            pos_args, options = parse_options(args, options_only_first=re_maxsplit != 0)
            split_args = (
                re.split(r"\s+", pos_args, maxsplit=re_maxsplit)
                if re_maxsplit >= 0
                else [pos_args]
            )
            if min_args and not pos_args or len(split_args) < min_args:
                print_error(
                    f'Too few arguments for command "/{cmd}" (help on command: /help {cmd})'
                )
                return
            result = f(buffer, split_args, options)
            if result is not None:
                run_async(result)
            return

        c = Command(cmd, top_level, "", "", "", completion, wrapper, alias)
        shared.commands[cmd] = c

        return wrapper

    return decorator


def list_workspaces(workspace_name: Optional[str] = None, detailed_list: bool = False):
    weechat.prnt("", "")
    weechat.prnt("", "All workspaces:")
    for workspace in shared.workspaces.values():
        display_workspace(workspace, detailed_list)


def display_workspace(workspace: SlackWorkspace, detailed_list: bool):
    if workspace.is_connected:
        num_pvs = len(
            [
                conversation
                for conversation in workspace.open_conversations.values()
                if conversation.buffer_type == "private"
            ]
        )
        num_channels = len(workspace.open_conversations) - num_pvs
        weechat.prnt(
            "",
            f" * "
            f"{with_color('chat_server', workspace.name)} "
            f"{with_color('chat_delimiters', '[')}"
            f"connected"
            f"{with_color('chat_delimiters', ']')}"
            f", nick: {workspace.my_user.nick.format()}"
            f", {num_channels} channel(s), {num_pvs} pv",
        )
    elif workspace.is_connecting:
        weechat.prnt(
            "",
            f"   {with_color('chat_server', workspace.name)} "
            f"{with_color('chat_delimiters', '[')}"
            f"connecting"
            f"{with_color('chat_delimiters', ']')}",
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


@weechat_command("%(slack_workspaces)|-all", max_split=0)
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


@weechat_command("%(slack_workspaces)|-all", max_split=0)
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
    if isinstance(slack_buffer, SlackMessageBuffer):
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


@weechat_command("%(nicks)", min_args=1, max_split=0, alias="query")
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

    user_ids = [user.id for user in users]
    await create_conversation_for_users(slack_buffer.workspace, user_ids)


async def get_conversation_from_args(buffer: str, args: List[str], options: Options):
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

    conversation_name = removeprefix(args[0].strip(), "#")
    all_conversations = get_resolved_futures(workspace.conversations.values())
    for conversation in all_conversations:
        if conversation.name() == conversation_name:
            return conversation

    if workspace.api.edgeapi.is_available:
        results = await workspace.api.edgeapi.fetch_channels_search(conversation_name)
        for channel_info in results["results"]:
            if channel_info["name"] == conversation_name:
                return await workspace.conversations[channel_info["id"]]

    print_error(f'Conversation "{conversation_name}" not found')


@weechat_command("", alias="join")
async def command_slack_join(buffer: str, args: List[str], options: Options):
    conversation = await get_conversation_from_args(buffer, args, options)
    if conversation is not None:
        await conversation.api.conversations_join(conversation.id)
        await conversation.open_buffer(switch=not options.get("noswitch"))


@weechat_command("", alias="part")
async def command_slack_part(buffer: str, args: List[str], options: Options):
    conversation = await get_conversation_from_args(buffer, args, options)
    if conversation is not None:
        await conversation.part()


@weechat_command("%(threads)", min_args=1, alias="thread")
async def command_slack_thread(buffer: str, args: List[str], options: Options):
    slack_buffer = shared.buffers.get(buffer)
    if isinstance(slack_buffer, SlackConversation):
        await slack_buffer.open_thread(args[0], switch=True)


async def _clean_thread_preview(
    text: str, workspace: SlackWorkspace, max_len: int = 70
) -> str:
    """Clean up message text for thread preview display."""
    # Remove URLs: <https://...|display> or <https://...>
    text = re.sub(r"<https?://[^>|]+\|([^>]+)>", r"\1", text)  # Keep display text
    text = re.sub(r"<https?://[^>]+>", "[link]", text)  # Replace bare URLs

    # Resolve user mentions: <@USERID> -> @username
    user_pattern = re.compile(r"<@([A-Z0-9]+)>")
    for match in user_pattern.finditer(text):
        user_id = match.group(1)
        try:
            user = await workspace.users[user_id]
            text = text.replace(match.group(0), f"@{user.nick.format()}")
        except Exception:
            text = text.replace(match.group(0), "@someone")

    # Resolve channel mentions: <#CHANNELID|name> -> #name, <#CHANNELID> -> #name
    text = re.sub(r"<#[A-Z0-9]+\|([^>]+)>", r"#\1", text)
    channel_pattern = re.compile(r"<#([A-Z0-9]+)>")
    for match in channel_pattern.finditer(text):
        channel_id = match.group(1)
        try:
            conv = await workspace.conversations[channel_id]
            text = text.replace(match.group(0), f"#{conv.name()}")
        except Exception:
            text = text.replace(match.group(0), "#channel")

    # Resolve subteam mentions: <!subteam^ID|@name> or <!subteam^ID>
    text = re.sub(r"<!subteam\^[A-Z0-9]+\|@([^>]+)>", r"@\1", text)
    subteam_pattern = re.compile(r"<!subteam\^([A-Z0-9]+)>")
    for match in subteam_pattern.finditer(text):
        subteam_id = match.group(1)
        try:
            usergroup = await workspace.usergroups[subteam_id]
            text = text.replace(match.group(0), f"@{usergroup.handle}")
        except Exception:
            text = text.replace(match.group(0), "@group")

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Truncate
    if len(text) > max_len:
        text = text[:max_len] + "..."

    return text


@weechat_command("-all|-dump|%(slack_workspaces)")
async def command_slack_threads(buffer: str, args: List[str], options: Options):
    """List subscribed threads with unread messages (session tokens only).

    Usage:
        /slack threads        - List threads with unreads
        /slack threads -all   - List all subscribed threads (including read)
        /slack threads <N>    - Open thread number N
        /slack threads -dump  - Dump raw JSON to ~/threads.json
    """
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer is None:
        print_error("Must be run from a slack buffer")
        return

    workspace = slack_buffer.workspace
    if workspace.token_type != "session":
        print_error("The /slack threads command only works with session tokens")
        return

    # Check if user wants to open a specific thread by number
    if args[0] and args[0].isdigit():
        thread_num = int(args[0])
        if not workspace.cached_thread_subscriptions:
            print_error(
                "No cached threads. Run /slack threads first to fetch the list."
            )
            return

        threads = workspace.cached_thread_subscriptions
        if thread_num < 1 or thread_num > len(threads):
            print_error(f"Invalid thread number. Must be between 1 and {len(threads)}.")
            return

        thread = threads[thread_num - 1]
        channel_id = thread["root_msg"]["channel"]
        thread_ts = SlackTs(thread["root_msg"]["thread_ts"])

        # Get or open the conversation
        conversation = await workspace.conversations[channel_id]
        if conversation.buffer_pointer is None:
            await conversation.open_buffer()

        # Fetch the thread to load the parent message
        parent_message, _ = await conversation.fetch_replies(thread_ts)

        # Create thread buffer if needed and open it
        if parent_message.thread_buffer is None:
            parent_message.thread_buffer = SlackThread(parent_message)
        await parent_message.thread_buffer.open_buffer(switch=True)
        return

    workspace.print("Fetching thread subscriptions...")

    try:
        response = await workspace.api.fetch_subscriptions_thread_get_view(limit=50)
    except Exception as e:
        print_error(f"Failed to fetch threads: {e}")
        return

    # Dump to file if -dump option
    if options.get("dump"):
        import os

        output_path = os.path.expanduser("~/threads.json")
        with open(output_path, "w") as f:
            json.dump(response, f, indent=2)
        workspace.print(f"Raw JSON written to {output_path}")

    if not response.get("ok"):
        error = response.get("error", "unknown error")
        workspace.print(f"Error: {error}")
        return

    all_threads = response.get("threads", [])

    # Filter to only threads with unreads, unless -all is specified
    show_all = options.get("all")
    if show_all:
        threads = all_threads
    else:
        threads = [t for t in all_threads if t.get("unread_replies")]

    # Cache the displayed threads for later reference (so numbers match)
    workspace.cached_thread_subscriptions = threads

    # Check for mentions (user's ID appears in unread replies)
    my_user_id = workspace.my_user.id
    threads_with_mentions = 0
    for thread in threads:
        for reply in thread.get("unread_replies", []):
            reply_text = reply.get("text", "")
            if f"<@{my_user_id}>" in reply_text:
                threads_with_mentions += 1
                break

    # Summary line
    has_more = response.get("has_more", False)
    more_indicator = "+" if has_more else ""
    mention_info = (
        f", {with_color('lightred', str(threads_with_mentions) + ' with mentions')}"
        if threads_with_mentions
        else ""
    )
    workspace.print(
        f"Threads with unreads: {with_color('bold', str(len(threads)) + more_indicator)}{mention_info}"
    )
    workspace.print("")

    for i, thread in enumerate(threads, 1):
        root_msg = thread.get("root_msg", {})
        channel_id = root_msg.get("channel", "unknown")
        root_text = await _clean_thread_preview(root_msg.get("text", ""), workspace)

        unread_count = len(thread.get("unread_replies", []))

        # Check if this thread has a mention for the user
        has_mention = False
        for reply in thread.get("unread_replies", []):
            if f"<@{my_user_id}>" in reply.get("text", ""):
                has_mention = True
                break

        # Try to get channel name
        channel_name = channel_id
        if channel_id in workspace.conversations:
            try:
                conv = await workspace.conversations[channel_id]
                channel_name = conv.name_with_prefix("short_name_without_padding")
            except Exception:
                pass

        # Format unread count with color (lightred for mentions, yellow otherwise)
        unread_str = with_color(
            "lightred" if has_mention else "yellow", str(unread_count)
        )
        mention_marker = with_color("lightred", " @") if has_mention else ""

        workspace.print(
            f"  {with_color('bold', str(i)):>3}. {with_color('chat_channel', channel_name)} "
            f"({unread_str} unread){mention_marker}"
        )
        workspace.print(f"       {with_color('darkgray', root_text)}")

    if has_more:
        workspace.print("")
        workspace.print(
            with_color("darkgray", "(more threads available, showing first 50)")
        )
    workspace.print("")
    workspace.print("Use /slack threads <N> to open a thread")


@weechat_command("-alsochannel|-memessage|%(threads)", min_args=1, alias="reply")
async def command_slack_reply(buffer: str, args: List[str], options: Options):
    slack_buffer = shared.buffers.get(buffer)

    broadcast = bool(options.get("alsochannel"))
    me_message = bool(options.get("memessage"))
    if broadcast and me_message:
        print_error(
            "Using both -alsochannel and -memessage simultaneously isn't supported"
        )
        return
    elif broadcast:
        message_type = "broadcast"
    elif me_message:
        message_type = "me_message"
    else:
        message_type = "standard"

    if isinstance(slack_buffer, SlackThread):
        await slack_buffer.post_message(args[0], message_type=message_type)
    elif isinstance(slack_buffer, SlackConversation):
        split_args = re.split(r"\s+", args[0], maxsplit=1)
        if len(split_args) < 2:
            print_error(
                'Too few arguments for command "/slack reply" (help on command: /help slack reply)'
            )
            return
        thread_ts = slack_buffer.ts_from_hash_or_index(split_args[0])
        if thread_ts is None:
            print_message_not_found_error(split_args[0])
            return
        await slack_buffer.post_message(
            split_args[1], thread_ts, message_type=message_type
        )


@weechat_command("", min_args=1, alias="me")
async def command_slack_memessage(buffer: str, args: List[str], options: Options):
    slack_buffer = shared.buffers.get(buffer)
    if isinstance(slack_buffer, SlackMessageBuffer):
        await slack_buffer.post_message(args[0], message_type="me_message")


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
    await slack_buffer.api.set_presence(new_presence)


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
        slack_buffer.workspace.print(
            f"Muted conversations: {', '.join(conversation_names)}"
        )
        return

    muted_channels = set(slack_buffer.workspace.muted_channels)
    muted_channels ^= {slack_buffer.id}
    await slack_buffer.api.set_muted_channels(muted_channels)
    muted_str = "Muted" if slack_buffer.id in muted_channels else "Unmuted"
    slack_buffer.workspace.print(
        f"{muted_str} channel {slack_buffer.name_with_prefix('short_name_without_padding')}",
    )


@weechat_command("channels|users", max_split=1)
async def command_slack_search(buffer: str, args: List[str], options: Options):
    if args[0] == "":
        search_buffer = next(
            (
                search_buffer
                for workspace in shared.workspaces.values()
                for search_buffer in workspace.search_buffers.values()
                if search_buffer.buffer_pointer == buffer
            ),
            None,
        )
        if search_buffer is not None:
            if options.get("up"):
                search_buffer.selected_line -= 1
            elif options.get("down"):
                search_buffer.selected_line += 1
            elif options.get("mark"):
                search_buffer.mark_line(search_buffer.selected_line)
            elif options.get("join_channel"):
                await search_buffer.join_channel()
            else:
                print_error("No search action specified")
    else:
        slack_buffer = shared.buffers.get(buffer)
        if slack_buffer is None:
            return

        if args[0] == "channels" or args[0] == "users":
            search_buffer = slack_buffer.workspace.search_buffers.get(args[0])
            query = args[1] if len(args) > 1 else None
            if search_buffer is not None:
                await search_buffer.open_buffer(switch=True, query=query)
            else:
                slack_buffer.workspace.search_buffers[args[0]] = SlackSearchBuffer(
                    slack_buffer.workspace, args[0], query
                )
        else:
            print_error(f"Unknown search type: {args[0]}")


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


@weechat_command("tasks|buffer|open_buffer|replay_events|errors|error", max_split=0)
async def command_slack_debug(buffer: str, args: List[str], options: Options):
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
    elif args[0] == "replay_events":
        slack_buffer = shared.buffers.get(buffer)
        if slack_buffer is None:
            print_error("Must be run from a slack buffer")
            return
        with open(args[1]) as f:
            for line in f:
                first_brace_pos = line.find("{")
                if first_brace_pos == -1:
                    continue
                event = json.loads(line[first_brace_pos:])
                await slack_buffer.workspace.ws_recv(event)
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
            await slack_buffer.api.clear_user_status()
        elif slack_buffer and len(status) > 0:
            await slack_buffer.api.set_user_status(status)
        else:
            print_error(
                'Too few arguments for command "/slack status" (help on command: /help slack status)'
            )
    else:
        print_error("Run the command in a slack buffer")


def _get_conversation_from_buffer(
    slack_buffer: SlackBuffer,
) -> Optional[SlackConversation]:
    if isinstance(slack_buffer, SlackConversation):
        return slack_buffer
    elif isinstance(slack_buffer, SlackThread):
        return slack_buffer.parent.conversation
    return None


def _get_linkarchive_url(
    slack_buffer: SlackBuffer,
    message_ts: Optional[SlackTs],
) -> str:
    url = f"https://{slack_buffer.workspace.domain}.slack.com/"
    conversation = _get_conversation_from_buffer(slack_buffer)
    if conversation is not None:
        url += f"archives/{conversation.id}/"
        if message_ts is not None:
            message = conversation.messages[message_ts]
            url += f"p{message.ts.major}{message.ts.minor:0>6}"
            if message.thread_ts is not None:
                url += f"?thread_ts={message.thread_ts}&cid={conversation.id}"
    return url


@weechat_command("%(threads)")
def command_slack_linkarchive(buffer: str, args: List[str], options: Options):
    """
    /slack linkarchive [message_id]
    Place a link to the conversation or message in the input bar.
    Use cursor or mouse mode to get the id.
    """
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer is None:
        return

    if isinstance(slack_buffer, SlackMessageBuffer) and args[0]:
        ts = slack_buffer.ts_from_hash_or_index(args[0])
        if ts is None:
            print_message_not_found_error(args[0])
            return
    else:
        ts = None

    url = _get_linkarchive_url(slack_buffer, ts)
    weechat.command(buffer, f"/input insert {url}")


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
    for c in shared.commands.values():
        if c.alias == cmd:
            return c, cmd_args
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


async def set_away(workspaces: Iterable[SlackWorkspace], away_message: str):
    for workspace in workspaces:
        if not workspace.is_connected:
            continue
        if away_message:
            await workspace.api.set_presence("away")
            await workspace.api.set_user_status(away_message)
        else:
            await workspace.api.set_presence("active")
            await workspace.api.clear_user_status()


def away_cb(data: str, buffer: str, command: str) -> int:
    command_split = command.strip().split(None, maxsplit=1)
    args_split1 = (
        command_split[1].strip().split(None, maxsplit=1)
        if len(command_split) > 1
        else []
    )

    if args_split1 and args_split1[0] == "-all":
        away_message = args_split1[1] if len(args_split1) > 1 else ""
        workspaces = shared.workspaces.values()
    else:
        away_message = command_split[1] if len(command_split) > 1 else ""
        slack_buffer = shared.buffers.get(buffer)
        if slack_buffer is None:
            return weechat.WEECHAT_RC_OK
        workspaces = [slack_buffer.workspace]

    run_async(set_away(workspaces, away_message.strip()))
    return weechat.WEECHAT_RC_OK


async def mark_read(slack_buffer: SlackMessageBuffer):
    # Sleep so the read marker is updated before we run slack_buffer.mark_read
    await sleep(1)
    await slack_buffer.mark_read()


def buffer_set_unread_cb(data: str, buffer: str, command: str) -> int:
    slack_buffer = shared.buffers.get(buffer)
    if isinstance(slack_buffer, SlackMessageBuffer):
        run_async(mark_read(slack_buffer))
    return weechat.WEECHAT_RC_OK


def focus_event_cb(data: str, signal: str, hashtable: Dict[str, str]) -> int:
    tags = hashtable["_chat_line_tags"].split(",")
    for tag in tags:
        ts = ts_from_tag(tag)
        if ts is not None:
            break
    else:
        return weechat.WEECHAT_RC_OK

    buffer_pointer = hashtable["_buffer"]
    slack_buffer = shared.buffers.get(buffer_pointer)
    if not isinstance(slack_buffer, SlackMessageBuffer):
        return weechat.WEECHAT_RC_OK

    conversation = _get_conversation_from_buffer(slack_buffer)
    if conversation is None:
        return weechat.WEECHAT_RC_OK

    message_hash = f"${conversation.message_hashes[ts]}"

    if data not in focus_events:
        print_error(f"Unknown focus event: {data}")
        return weechat.WEECHAT_RC_OK

    if data == "auto":
        emoji_match = re.match(EMOJI_CHAR_OR_NAME_REGEX_STRING, hashtable["_chat_eol"])
        if emoji_match is not None:
            emoji = emoji_match.group("emoji_char") or emoji_match.group("emoji_name")
            run_async(conversation.send_change_reaction(ts, emoji, "toggle"))
        else:
            weechat.command(buffer_pointer, f"/input insert {message_hash}")
    elif data == "message":
        weechat.command(buffer_pointer, f"/input insert {message_hash}")
    elif data == "delete":
        run_async(conversation.api.chat_delete_message(conversation, ts))
    elif data == "linkarchive":
        url = _get_linkarchive_url(slack_buffer, ts)
        weechat.command(buffer_pointer, f"/input insert {url}")
    elif data == "reply":
        weechat.command(buffer_pointer, f"/input insert /reply {message_hash}\\x20")
    elif data == "thread":
        run_async(conversation.open_thread(message_hash, switch=True))
    else:
        assert_never(data)
    return weechat.WEECHAT_RC_OK


def python_eval_slack_cb(data: str, buffer: str, command: str) -> int:
    slack_buffer = shared.buffers.get(buffer)
    if slack_buffer is None:
        print_error("Must be run from a slack buffer")
        return weechat.WEECHAT_RC_OK_EAT
    args = command.split(" ", maxsplit=2)
    code = compile(
        args[2], "<string>", "exec", flags=getattr(ast, "PyCF_ALLOW_TOP_LEVEL_AWAIT", 0)
    )
    coroutine = eval(code)
    if coroutine is not None:
        run_async(coroutine)
    return weechat.WEECHAT_RC_OK_EAT


def register_commands():
    weechat.hook_command_run("/away", get_callback_name(away_cb), "")
    weechat.hook_command_run(
        "/buffer set unread", get_callback_name(buffer_set_unread_cb), ""
    )
    weechat.hook_command_run(
        "/buffer set unread *", get_callback_name(buffer_set_unread_cb), ""
    )
    weechat.hook_command_run(
        "/input set_unread_current_buffer", get_callback_name(buffer_set_unread_cb), ""
    )
    weechat.hook_command_run(
        "/python eval_slack *", get_callback_name(python_eval_slack_cb), ""
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
        if command.alias:
            weechat.hook_command(
                command.alias,
                command.description,
                command.args,
                command.args_description,
                "%(slack_commands)|%*",
                get_callback_name(command_cb),
                command.alias,
            )

    for focus_event in focus_events:
        weechat.hook_hsignal(
            f"slack_focus_{focus_event}",
            get_callback_name(focus_event_cb),
            focus_event,
        )

    weechat.key_bind(
        "mouse",
        {
            "@chat(python.*):button2": "hsignal:slack_focus_auto",
        },
    )
    weechat.key_bind(
        "cursor",
        {
            "@chat(python.*):D": "hsignal:slack_focus_delete",
            "@chat(python.*):L": "hsignal:slack_focus_linkarchive; /cursor stop",
            "@chat(python.*):M": "hsignal:slack_focus_message; /cursor stop",
            "@chat(python.*):R": "hsignal:slack_focus_reply; /cursor stop",
            "@chat(python.*):T": "hsignal:slack_focus_thread; /cursor stop",
        },
    )

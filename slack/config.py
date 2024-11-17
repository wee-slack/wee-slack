from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional, Tuple

import weechat

from slack.log import print_error
from slack.shared import shared
from slack.slack_conversation import invalidate_nicklists, update_buffer_props
from slack.slack_workspace import SlackWorkspace, workspace_get_buffer_to_merge_with
from slack.util import get_callback_name
from slack.weechat_config import (
    WeeChatColor,
    WeeChatConfig,
    WeeChatOption,
    WeeChatOptionType,
    WeeChatSection,
)

if TYPE_CHECKING:
    from typing_extensions import Literal


class SlackConfigSectionColor:
    def __init__(self, weechat_config: WeeChatConfig):
        self._section = WeeChatSection(weechat_config, "color")

        self.buflist_muted_conversation = WeeChatOption(
            self._section,
            "buflist_muted_conversation",
            "text color for muted conversations in the buflist",
            WeeChatColor("darkgray"),
            callback_change=self.config_change_buflist_muted_conversation_cb,
        )

        self.channel_mention = WeeChatOption(
            self._section,
            "channel_mention",
            "text color for mentioned channel names in the chat",
            WeeChatColor("blue"),
        )

        self.deleted_message = WeeChatOption(
            self._section,
            "deleted_message",
            "text color for a deleted message",
            WeeChatColor("red"),
        )

        self.disconnected = WeeChatOption(
            self._section,
            "disconnected",
            "text color for the disconnected text",
            WeeChatColor("red"),
        )

        self.edited_message_suffix = WeeChatOption(
            self._section,
            "edited_message_suffix",
            "text color for the suffix after an edited message",
            WeeChatColor("095"),
        )

        self.loading = WeeChatOption(
            self._section,
            "loading",
            "text color for the loading text",
            WeeChatColor("yellow"),
        )

        self.message_join = WeeChatOption(
            self._section,
            "message_join",
            "color for text in join messages",
            WeeChatColor("green"),
            parent_option="irc.color.message_join",
        )

        self.message_quit = WeeChatOption(
            self._section,
            "message_quit",
            "color for text in part messages",
            WeeChatColor("red"),
            parent_option="irc.color.message_quit",
        )

        self.reaction_suffix = WeeChatOption(
            self._section,
            "reaction_suffix",
            "color for the reactions after a message",
            WeeChatColor("darkgray"),
        )

        self.reaction_self_suffix = WeeChatOption(
            self._section,
            "reaction_self_suffix",
            "color for the reactions after a message, for reactions you have added",
            WeeChatColor("blue"),
        )

        self.render_error = WeeChatOption(
            self._section,
            "render_error",
            "color for displaying rendering errors in a message",
            WeeChatColor("red"),
        )

        self.search_line_marked_bg = WeeChatOption(
            self._section,
            "search_line_marked_bg",
            "background color for a marked line in search buffers",
            WeeChatColor("17"),
        )

        self.search_line_selected_bg = WeeChatOption(
            self._section,
            "search_line_selected_bg",
            "background color for the selected line in search buffers",
            WeeChatColor("24"),
        )

        self.search_marked = WeeChatOption(
            self._section,
            "search_marked",
            "color for mark indicator in search buffers",
            WeeChatColor("brown"),
        )

        self.search_marked_selected = WeeChatOption(
            self._section,
            "search_marked_selected",
            "color for mark indicator on the selected line in search buffers",
            WeeChatColor("yellow"),
        )

        self.user_mention = WeeChatOption(
            self._section,
            "user_mention",
            "text color for mentioned user names in the chat",
            WeeChatColor("blue"),
        )

        self.user_mention_nick_color = WeeChatOption(
            self._section,
            "user_mention_nick_color",
            "",
            False,
            callback_change=self.config_change_user_mention_nick_color_cb,
        )

        self.usergroup_mention = WeeChatOption(
            self._section,
            "usergroup_mention",
            "text color for mentioned user group names in the chat",
            WeeChatColor("blue"),
        )

    def config_change_buflist_muted_conversation_cb(
        self, option: WeeChatOption[WeeChatOptionType], parent_changed: bool
    ):
        update_buffer_props()

    def config_change_user_mention_nick_color_cb(
        self, option: WeeChatOption[WeeChatOptionType], parent_changed: bool
    ):
        self.user_mention.enabled = not option.value


class SlackConfigSectionLook:
    def __init__(self, weechat_config: WeeChatConfig):
        self._section = WeeChatSection(weechat_config, "look")

        self.bot_user_suffix = WeeChatOption(
            self._section,
            "bot_user_suffix",
            "the suffix appended to nicks to indicate a bot",
            " :]",
        )

        self.thread_broadcast_prefix = WeeChatOption(
            self._section,
            "thread_broadcast_prefix",
            "prefix to distinguish thread messages that were also sent to the channel, when display_thread_replies_in_channel is enabled",
            "+",
        )

        self.color_nicks_in_nicklist = WeeChatOption(
            self._section,
            "color_nicks_in_nicklist",
            "use nick color in nicklist",
            False,
            parent_option="irc.look.color_nicks_in_nicklist",
            callback_change=self.config_change_color_nicks_in_nicklist_cb,
        )

        self.color_message_attachments: WeeChatOption[
            Literal["prefix", "all", "none"]
        ] = WeeChatOption(
            self._section,
            "color_message_attachments",
            "colorize attachments in a message: prefix = only colorize the prefix, all = colorize the whole line, none = don't colorize",
            "prefix",
            string_values=("prefix", "all", "none"),
        )

        self.display_link_previews: WeeChatOption[
            Literal["always", "only_internal", "never"]
        ] = WeeChatOption(
            self._section,
            "display_link_previews",
            "display previews of URLs in messages: always = always display, only_internal = only display for URLs to messages in the workspace, never = never display",
            "always",
            string_values=("always", "only_internal", "never"),
        )

        self.display_reaction_nicks = WeeChatOption(
            self._section,
            "display_reaction_nicks",
            "display the name of the reacting user(s) after each reaction; can be overridden per buffer with the buffer localvar display_reaction_nicks",
            False,
        )

        self.display_thread_replies_in_channel = WeeChatOption(
            self._section,
            "display_thread_replies_in_channel",
            "display thread replies in the parent channel; can be overridden per buffer with the buffer localvar display_thread_replies_in_channel; note that it only takes effect for new messages; note that due to limitations in the Slack API, on load only thread messages for parents that are in the buffer and thread messages in subscribed threads will be displayed (but all thread messages received while connected will be displayed)",
            False,
        )

        self.external_user_suffix = WeeChatOption(
            self._section,
            "external_user_suffix",
            "the suffix appended to nicks to indicate external users",
            "*",
        )

        self.leave_channel_on_buffer_close = WeeChatOption(
            self._section,
            "leave_channel_on_buffer_close",
            "leave channel when a buffer is closed",
            True,
        )

        self.muted_conversations_notify: WeeChatOption[
            Literal["none", "personal_highlights", "all_highlights", "all"]
        ] = WeeChatOption(
            self._section,
            "muted_conversations_notify",
            "notify level to set for messages in muted conversations; none: don't notify for any messages; personal_highlights: only notify for personal highlights, i.e. not @channel and @here; all_highlights: notify for all highlights, but not other messages; all: notify for all messages, like other channels; note that this doesn't affect messages in threads you are subscribed to or in open thread buffers, those will always notify",
            "personal_highlights",
            string_values=("none", "personal_highlights", "all_highlights", "all"),
        )

        self.notify_subscribed_threads: WeeChatOption[
            Literal["auto", "unless_thread_buffer", "always", "never"]
        ] = WeeChatOption(
            self._section,
            "notify_subscribed_threads",
            "send a message to the workspace buffer to notify you of new messages in threads you are subscribed to: auto = only notify if the thread buffer is not open and display_thread_replies_in_channel for the channel is false, unless_thread_buffer = only notify if the thread buffer is not open, always = always notify, never = never notify",
            "auto",
            string_values=("auto", "unless_thread_buffer", "always", "never"),
        )

        self.part_closes_buffer = WeeChatOption(
            self._section,
            "part_closes_buffer",
            "close buffer when /slack part is issued on a channel",
            False,
            parent_option="irc.look.part_closes_buffer",
        )

        self.render_emoji_as: WeeChatOption[Literal["emoji", "name", "both"]] = (
            WeeChatOption(
                self._section,
                "render_emoji_as",
                "show emojis as: emoji = the emoji unicode character, name = the emoji name, both = both the emoji name and the emoji character",
                "emoji",
                string_values=("emoji", "name", "both"),
            )
        )

        self.render_url_as = WeeChatOption(
            self._section,
            "render_url_as",
            "format to render URLs (note: content is evaluated, see /help eval; ${url} is replaced by the URL link and ${text} is replaced by the URL text); the default format renders only the URL if the text is empty or is contained in the URL, otherwise it renders the text (underlined) first and then the URL in parentheses",
            "${if: ${text} == || ${url} =- ${text} ?${url}:${color:underline}${text}${color:-underline} (${url})}",
        )

        self.replace_space_in_nicks_with = WeeChatOption(
            self._section,
            "replace_space_in_nicks_with",
            "",
            "",
        )

        self.workspace_buffer: WeeChatOption[
            Literal["merge_with_core", "merge_without_core", "independent"]
        ] = WeeChatOption(
            self._section,
            "workspace_buffer",
            "merge workspace buffers; this option has no effect if a layout is saved and is conflicting with this value (see /help layout)",
            "merge_with_core",
            string_values=("merge_with_core", "merge_without_core", "independent"),
            parent_option="irc.look.server_buffer",
            callback_change=self.config_change_workspace_buffer_cb,
        )

        self.typing_status_nicks = WeeChatOption(
            self._section,
            "typing_status_nicks",
            'display nicks typing on the channel in bar item "typing" (option typing.look.enabled_nicks must be enabled)',
            True,
        )

        self.typing_status_self = WeeChatOption(
            self._section,
            "typing_status_self",
            "send self typing status to channels so that other users see when you are typing a message (option typing.look.enabled_self must be enabled)",
            True,
        )

        weechat.hook_config(
            "weechat.look.nick_color_*",
            get_callback_name(self.config_change_nick_colors_cb),
            "",
        )
        weechat.hook_config(
            "weechat.color.chat_nick_colors",
            get_callback_name(self.config_change_nick_colors_cb),
            "",
        )

    def config_change_color_nicks_in_nicklist_cb(
        self, option: WeeChatOption[WeeChatOptionType], parent_changed: bool
    ):
        invalidate_nicklists()

    def config_change_workspace_buffer_cb(
        self, option: WeeChatOption[WeeChatOptionType], parent_changed: bool
    ):
        for workspace in shared.workspaces.values():
            if workspace.buffer_pointer:
                weechat.buffer_unmerge(workspace.buffer_pointer, -1)

        buffer_to_merge_with = workspace_get_buffer_to_merge_with()
        if buffer_to_merge_with:
            for workspace in shared.workspaces.values():
                if (
                    workspace.buffer_pointer
                    and workspace.buffer_pointer != buffer_to_merge_with
                ):
                    weechat.buffer_merge(workspace.buffer_pointer, buffer_to_merge_with)

    def config_change_nick_colors_cb(self, data: str, option: str, value: str):
        invalidate_nicklists()
        return weechat.WEECHAT_RC_OK


class SlackConfigSectionWorkspace:
    def __init__(
        self,
        section: WeeChatSection,
        workspace_name: Optional[str],
        parent_config: Optional[SlackConfigSectionWorkspace],
    ):
        self._section = section
        self._workspace_name = workspace_name
        self._parent_config = parent_config

        self.api_token = self._create_option(
            "api_token",
            "The token (note: content is evaluated, see /help eval; workspace options are evaluated with ${workspace} replaced by the workspace name)",
            "",
            evaluate_func=self._evaluate_with_workspace_name,
        )

        self.api_cookies = self._create_option(
            "api_cookies",
            "The cookies (note: content is evaluated, see /help eval; workspace options are evaluated with ${workspace} replaced by the workspace name)",
            "",
            evaluate_func=self._evaluate_with_workspace_name,
        )

        self.auto_open_threads = self._create_option(
            "auto_open_threads",
            "automatically open thread buffers; see the other options starting with auto_open_threads for which threads to open; can be overridden per buffer with the buffer localvar auto_open_threads",
            False,
        )

        self.auto_open_threads_only_if_replies_not_in_channel = self._create_option(
            "auto_open_threads_only_if_replies_not_in_channel",
            "limit automatically opening threads to only threads in conversations where display_thread_replies_in_channel is disabled; can be overridden per buffer with the buffer localvar auto_open_threads_only_if_replies_not_in_channel",
            True,
        )

        self.auto_open_threads_only_subscribed = self._create_option(
            "auto_open_threads_only_subscribed",
            "limit automatically opening threads to only subscribed threads; note that only subscribed threads have a read status on the server, so on script load all messages in unsubscribed threads will be considered read; can be overridden per buffer with the buffer localvar auto_open_threads_only_subscribed",
            True,
        )

        self.auto_open_threads_only_unread = self._create_option(
            "auto_open_threads_only_unread",
            "limit automatically opening threads to only unread threads; note that only subscribed threads have a read status on the server, so this option only applies to subscribed threads; can be overridden per buffer with the buffer localvar auto_open_threads_only_unread",
            True,
        )

        self.autoconnect = self._create_option(
            "autoconnect",
            "automatically connect to workspace when WeeChat is starting",
            False,
        )

        self.keep_active: WeeChatOption[Literal["on_activity", "always"]] = (
            self._create_option(
                "keep_active",
                "keep your presence set to active: on_activity = set active when you interact with WeeChat (Slack sets you away after 30 minutes of inactivity), always = remain active as long as you're connected to the workspace",
                "on_activity",
                string_values=("on_activity", "always"),
            )
        )

        self.network_timeout = self._create_option(
            "network_timeout",
            "timeout (in seconds) for network requests",
            30,
        )

        self.nick_source: WeeChatOption[
            Literal["display_name", "real_name", "username"]
        ] = self._create_option(
            "nick_source",
            "property from the user profile to use as the nick",
            "display_name",
            string_values=("display_name", "real_name", "username"),
        )

    def _evaluate_with_workspace_name(self, value: str) -> str:
        return weechat.string_eval_expression(
            value, {}, {"workspace": self._workspace_name or ""}, {}
        )

    def _create_option(
        self,
        name: str,
        description: str,
        default_value: WeeChatOptionType,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        string_values: Tuple[WeeChatOptionType, ...] = (),
        evaluate_func: Optional[
            Callable[[WeeChatOptionType], WeeChatOptionType]
        ] = None,
    ) -> WeeChatOption[WeeChatOptionType]:
        if self._workspace_name:
            option_name = f"{self._workspace_name}.{name}"
        else:
            option_name = name

        if self._parent_config:
            parent_option = getattr(self._parent_config, name, None)
        else:
            parent_option = None

        return WeeChatOption(
            self._section,
            option_name,
            description,
            default_value,
            min_value,
            max_value,
            string_values,
            parent_option,
            evaluate_func=evaluate_func,
        )


def config_section_workspace_read_cb(
    data: str, config_file: str, section: str, option_name: str, value: Optional[str]
) -> int:
    option_split = option_name.split(".", maxsplit=1)
    if len(option_split) < 2:
        return weechat.WEECHAT_CONFIG_OPTION_SET_ERROR
    workspace_name, name = option_split
    if not workspace_name or not name:
        return weechat.WEECHAT_CONFIG_OPTION_SET_ERROR

    if workspace_name not in shared.workspaces:
        shared.workspaces[workspace_name] = SlackWorkspace(workspace_name)

    option = getattr(shared.workspaces[workspace_name].config, name, None)
    if option is None:
        return weechat.WEECHAT_CONFIG_OPTION_SET_OPTION_NOT_FOUND
    if not isinstance(option, WeeChatOption):
        return weechat.WEECHAT_CONFIG_OPTION_SET_ERROR

    if value is None or (
        shared.weechat_version < 0x03080000
        and value == ""
        and option.weechat_type != "string"
    ):
        rc = option.value_set_null()
    else:
        rc = option.value_set_as_str(value)
    if rc == weechat.WEECHAT_CONFIG_OPTION_SET_ERROR:
        print_error(f'error creating workspace option "{option_name}"')
    return rc


def config_section_workspace_write_for_old_weechat_cb(
    data: str, config_file: str, section_name: str
) -> int:
    if not weechat.config_write_line(config_file, section_name, ""):
        return weechat.WEECHAT_CONFIG_WRITE_ERROR

    for workspace in shared.workspaces.values():
        for option in vars(workspace.config).values():
            if (
                isinstance(option, WeeChatOption)
                and option.pointer is not None
                and (
                    option.weechat_type != "string"
                    or not weechat.config_option_is_null(option.pointer)
                )
            ):
                if not weechat.config_write_option(config_file, option.pointer):
                    return weechat.WEECHAT_CONFIG_WRITE_ERROR

    return weechat.WEECHAT_CONFIG_WRITE_OK


class SlackConfig:
    def __init__(self):
        self.weechat_config = WeeChatConfig("slack")
        self.color = SlackConfigSectionColor(self.weechat_config)
        self.look = SlackConfigSectionLook(self.weechat_config)
        self._section_workspace_default = WeeChatSection(
            self.weechat_config, "workspace_default"
        )
        # WeeChat < 3.8 sends null as an empty string to callback_read, so in
        # order to distinguish them, don't write the null values to the config
        # See https://github.com/weechat/weechat/pull/1843
        callback_write = (
            get_callback_name(config_section_workspace_write_for_old_weechat_cb)
            if shared.weechat_version < 0x03080000
            else ""
        )
        self._section_workspace = WeeChatSection(
            self.weechat_config,
            "workspace",
            callback_read=get_callback_name(config_section_workspace_read_cb),
            callback_write=callback_write,
        )
        self._workspace_default = SlackConfigSectionWorkspace(
            self._section_workspace_default, None, None
        )

    def config_read(self):
        weechat.config_read(self.weechat_config.pointer)

    def create_workspace_config(self, workspace_name: str):
        if workspace_name in shared.workspaces:
            raise Exception(
                f"Failed to create workspace config, already exists: {workspace_name}"
            )
        return SlackConfigSectionWorkspace(
            self._section_workspace, workspace_name, self._workspace_default
        )

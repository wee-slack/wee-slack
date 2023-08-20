from __future__ import annotations

from typing import Optional

import weechat

from slack.log import print_error
from slack.shared import shared
from slack.slack_conversation import invalidate_nicklists
from slack.slack_workspace import SlackWorkspace
from slack.util import get_callback_name
from slack.weechat_config import (
    WeeChatColor,
    WeeChatConfig,
    WeeChatOption,
    WeeChatOptionType,
    WeeChatSection,
)


class SlackConfigSectionColor:
    def __init__(self, weechat_config: WeeChatConfig):
        self._section = WeeChatSection(weechat_config, "color")

        self.channel_mention_color = WeeChatOption(
            self._section,
            "channel_mention_color",
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
            "text color for the [:wave:(@user)] suffix on messages that have"
            " reactions attached to them.",
            WeeChatColor("darkgray"),
        )

        self.user_mention_color = WeeChatOption(
            self._section,
            "user_mention_color",
            "text color for mentioned user names in the chat",
            WeeChatColor("blue"),
        )

        self.usergroup_mention_color = WeeChatOption(
            self._section,
            "usergroup_mention_color",
            "text color for mentioned user group names in the chat",
            WeeChatColor("blue"),
        )


class SlackConfigSectionLook:
    def __init__(self, weechat_config: WeeChatConfig):
        self._section = WeeChatSection(weechat_config, "look")

        self.bot_user_suffix = WeeChatOption(
            self._section,
            "bot_user_suffix",
            "the suffix appended to nicks to indicate a bot",
            " :]",
        )

        self.color_nicks_in_nicklist = WeeChatOption(
            self._section,
            "color_nicks_in_nicklist",
            "use nick color in nicklist",
            False,
            parent_option="irc.look.color_nicks_in_nicklist",
            callback_change=self.config_change_color_nicks_in_nicklist_cb,
        )

        self.external_user_suffix = WeeChatOption(
            self._section,
            "external_user_suffix",
            "the suffix appended to nicks to indicate external users",
            "*",
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
            "",
            "",
        )

        self.api_cookies = self._create_option(
            "api_cookies",
            "",
            "",
        )

        self.autoconnect = self._create_option(
            "autoconnect",
            "automatically connect to workspace when WeeChat is starting",
            False,
        )

        self.network_timeout = self._create_option(
            "network_timeout",
            "timeout (in seconds) for network requests",
            30,
        )

        self.use_real_names = self._create_option(
            "use_real_names",
            "use real names as the nicks for all users. When this is"
            " false, display names will be used if set, with a fallback"
            " to the real name if display name is not set",
            False,
        )

    def _create_option(
        self,
        name: str,
        description: str,
        default_value: WeeChatOptionType,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        string_values: Optional[str] = None,
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
        )


def config_section_workspace_read_cb(
    data: str, config_file: str, section: str, option_name: str, value: Optional[str]
) -> int:
    option_split = option_name.split(".", 1)
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
            if isinstance(option, WeeChatOption):
                if (
                    option.weechat_type != "string"
                    or not weechat.config_option_is_null(
                        option._pointer  # pyright: ignore [reportPrivateUsage]
                    )
                ):
                    if not weechat.config_write_option(
                        config_file,
                        option._pointer,  # pyright: ignore [reportPrivateUsage]
                    ):
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

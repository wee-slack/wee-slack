from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Optional, TypeVar, Union, cast

import weechat

from slack.shared import shared


class WeeChatColor(str):
    pass


@dataclass
class WeeChatConfig:
    name: str

    def __post_init__(self):
        self.pointer = weechat.config_new(self.name, "", "")


@dataclass
class WeeChatSection:
    weechat_config: WeeChatConfig
    name: str
    user_can_add_options: bool = False
    user_can_delete_options: bool = False
    callback_read: str = ""
    callback_write: str = ""

    def __post_init__(self):
        self.pointer = weechat.config_new_section(
            self.weechat_config.pointer,
            self.name,
            self.user_can_add_options,
            self.user_can_delete_options,
            self.callback_read,
            "",
            self.callback_write,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        )


WeeChatOptionTypes = Union[int, str]
WeeChatOptionType = TypeVar("WeeChatOptionType", bound=WeeChatOptionTypes)


@dataclass
class WeeChatOption(Generic[WeeChatOptionType]):
    section: WeeChatSection
    name: str
    description: str
    default_value: WeeChatOptionType
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    string_values: Optional[str] = None
    parent_option: Optional[WeeChatOption[WeeChatOptionType]] = None

    def __post_init__(self):
        self._pointer = self._create_weechat_option()

    @property
    def value(self) -> WeeChatOptionType:
        if weechat.config_option_is_null(self._pointer):
            if self.parent_option:
                return self.parent_option.value
            return self.default_value

        if isinstance(self.default_value, bool):
            return cast(WeeChatOptionType, weechat.config_boolean(self._pointer) == 1)
        if isinstance(self.default_value, int):
            return cast(WeeChatOptionType, weechat.config_integer(self._pointer))
        if isinstance(self.default_value, WeeChatColor):
            color = weechat.config_color(self._pointer)
            return cast(WeeChatOptionType, WeeChatColor(color))
        return cast(WeeChatOptionType, weechat.config_string(self._pointer))

    @value.setter
    def value(self, value: WeeChatOptionType):
        rc = self.value_set_as_str(str(value))
        if rc == weechat.WEECHAT_CONFIG_OPTION_SET_ERROR:
            raise Exception(f"Failed to value for option: {self.name}")

    def value_set_as_str(self, value: str) -> int:
        return weechat.config_option_set(self._pointer, value, 1)

    def value_set_null(self) -> int:
        if not self.parent_option:
            raise Exception(
                f"Can't set null value for option without parent: {self.name}"
            )
        return weechat.config_option_set_null(self._pointer, 1)

    @property
    def weechat_type(self) -> str:
        if self.string_values:
            return "integer"
        if isinstance(self.default_value, bool):
            return "boolean"
        if isinstance(self.default_value, int):
            return "integer"
        if isinstance(self.default_value, WeeChatColor):
            return "color"
        return "string"

    def _create_weechat_option(self) -> str:
        if self.parent_option:
            parent_option_name = (
                f"{self.parent_option.section.weechat_config.name}"
                f".{self.parent_option.section.name}"
                f".{self.parent_option.name}"
            )
            name = f"{self.name} << {parent_option_name}"
            default_value = None
            null_value_allowed = True
        else:
            name = self.name
            default_value = str(self.default_value)
            null_value_allowed = False

        value = None

        if shared.weechat_version < 0x3050000:
            default_value = str(self.default_value)
            value = default_value

        return weechat.config_new_option(
            self.section.weechat_config.pointer,
            self.section.pointer,
            name,
            self.weechat_type,
            self.description,
            self.string_values or "",
            self.min_value or -(2**31),
            self.max_value or 2**31 - 1,
            default_value,
            value,
            null_value_allowed,
            "",
            "",
            "",
            "",
            "",
            "",
        )

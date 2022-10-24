from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
from io import StringIO
import json
import os
import resource
from typing import (
    Any,
    Dict,
    Generator,
    Generic,
    TYPE_CHECKING,
    Tuple,
    TypeVar,
    Union,
    cast,
)
from typing import Awaitable, Coroutine
from urllib.parse import urlencode
from uuid import uuid4

import weechat


if TYPE_CHECKING:
    from slack_api import (
        SlackConversation,
        SlackConversationNotIm,
        SlackConversationIm,
    )
else:
    # To support running without slack types
    SlackConversation = Any
    SlackConversationNotIm = Any
    SlackConversationIm = Any

SCRIPT_NAME = "slack"
SCRIPT_AUTHOR = "Trygve Aaberge <trygveaa@gmail.com>"
SCRIPT_VERSION = "3.0.0"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Extends weechat for typing notification/search/etc on slack.com"
REPO_URL = "https://github.com/wee-slack/wee-slack"

### Basic classes

T = TypeVar("T")


class LogLevel(IntEnum):
    TRACE = 1
    DEBUG = 2
    INFO = 3
    WARN = 4
    ERROR = 5
    FATAL = 6


class HttpError(Exception):
    def __init__(self, url: str, return_code: int, http_status: int, error: str):
        super().__init__()
        self.url = url
        self.return_code = return_code
        self.http_status = http_status
        self.error = error


class Future(Awaitable[T]):
    def __init__(self):
        self.id = str(uuid4())

    def __await__(self) -> Generator[Future[T], T, T]:
        return (yield self)


class FutureProcess(Future[Tuple[str, int, str, str]]):
    pass


class FutureTimer(Future[Tuple[int]]):
    pass


class Task(Future[T]):
    def __init__(self, coroutine: Coroutine[Future[Any], Any, T], final: bool):
        super().__init__()
        self.coroutine = coroutine
        self.final = final


### Helpers


# TODO: Figure out what to do with print_error vs log
def print_error(message: str):
    weechat.prnt("", f"{weechat.prefix('error')}{SCRIPT_NAME}: {message}")


def log(level: LogLevel, message: str):
    if level >= LogLevel.INFO:
        print(level, message)


def available_file_descriptors():
    num_current_file_descriptors = len(os.listdir("/proc/self/fd/"))
    max_file_descriptors = min(resource.getrlimit(resource.RLIMIT_NOFILE))
    return max_file_descriptors - num_current_file_descriptors


### WeeChat classes


class WeeChatColor(str):
    pass


@dataclass
class WeeChatConfig:
    name: str

    def __post_init__(self):
        self.pointer = weechat.config_new(self.name, "", "")


def config_section_workspace_write_for_old_weechat_cb(
    data: str, config_file: str, section_name: str
) -> int:
    if not weechat.config_write_line(config_file, section_name, ""):
        return weechat.WEECHAT_CONFIG_WRITE_ERROR

    for workspace in workspaces.values():
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


@dataclass
class WeeChatSection:
    weechat_config: WeeChatConfig
    name: str
    user_can_add_options: bool = False
    user_can_delete_options: bool = False
    callback_read: Union[str, None] = None

    def __post_init__(self):
        # WeeChat < 3.8 sends null as an empty string to callback_read, so in
        # order to distinguish them, don't write the null values to the config
        # See https://github.com/weechat/weechat/pull/1843
        if weechat_version < 0x3080000 and self.callback_read:
            callback_write = config_section_workspace_write_for_old_weechat_cb.__name__
        else:
            callback_write = ""
        self.pointer = weechat.config_new_section(
            self.weechat_config.pointer,
            self.name,
            self.user_can_add_options,
            self.user_can_delete_options,
            self.callback_read or "",
            "",
            callback_write,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        )


WeeChatOptionType = TypeVar("WeeChatOptionType", bound=Union[int, str])


@dataclass
class WeeChatOption(Generic[WeeChatOptionType]):
    section: WeeChatSection
    name: str
    description: str
    default_value: WeeChatOptionType
    min_value: Union[int, None] = None
    max_value: Union[int, None] = None
    string_values: Union[str, None] = None
    parent_option: Union[WeeChatOption[WeeChatOptionType], None] = None

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

        if weechat_version < 0x3050000:
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


### WeeChat callbacks

active_tasks: Dict[str, Task[Any]] = {}
active_responses: Dict[str, Tuple[Any, ...]] = {}


def shutdown_cb():
    weechat.config_write(config.weechat_config.pointer)
    return weechat.WEECHAT_RC_OK


def weechat_task_cb(data: str, *args: Any) -> int:
    task = active_tasks.pop(data)
    task_runner(task, args)
    return weechat.WEECHAT_RC_OK


### WeeChat helpers


def task_runner(task: Task[Any], response: Any):
    while True:
        try:
            future = task.coroutine.send(response)
            if future.id in active_responses:
                response = active_responses.pop(future.id)
            else:
                if future.id in active_tasks:
                    raise Exception(
                        f"future.id in active_tasks, {future.id}, {active_tasks}"
                    )
                active_tasks[future.id] = task
                break
        except StopIteration as e:
            if task.id in active_tasks:
                task = active_tasks.pop(task.id)
                response = e.value
            else:
                if task.id in active_responses:
                    raise Exception(
                        f"task.id in active_responses, {task.id}, {active_responses}"
                    )
                if not task.final:
                    active_responses[task.id] = e.value
                break


def create_task(
    coroutine: Coroutine[Future[Any], Any, T], final: bool = False
) -> Task[T]:
    task = Task(coroutine, final)
    task_runner(task, None)
    return task


async def sleep(milliseconds: int):
    future = FutureTimer()
    weechat.hook_timer(milliseconds, 0, 1, weechat_task_cb.__name__, future.id)
    return await future


async def hook_process_hashtable(command: str, options: Dict[str, str], timeout: int):
    future = FutureProcess()
    log(
        LogLevel.DEBUG,
        f"hook_process_hashtable calling ({future.id}): command: {command}",
    )
    while available_file_descriptors() < 10:
        await sleep(10)
    weechat.hook_process_hashtable(
        command, options, timeout, weechat_task_cb.__name__, future.id
    )

    stdout = StringIO()
    stderr = StringIO()
    return_code = -1

    while return_code == -1:
        _, return_code, out, err = await future
        log(
            LogLevel.TRACE,
            f"hook_process_hashtable intermediary response ({future.id}): command: {command}",
        )
        stdout.write(out)
        stderr.write(err)

    out = stdout.getvalue()
    err = stderr.getvalue()
    log(
        LogLevel.DEBUG,
        f"hook_process_hashtable response ({future.id}): command: {command}, "
        f"return_code: {return_code}, response length: {len(out)}"
        + (f", error: {err}" if err else ""),
    )

    return command, return_code, out, err


async def http_request(
    url: str, options: Dict[str, str], timeout: int, max_retries: int = 5
) -> str:
    options["header"] = "1"
    _, return_code, out, err = await hook_process_hashtable(
        f"url:{url}", options, timeout
    )

    if return_code != 0 or err:
        if max_retries > 0:
            log(
                LogLevel.INFO,
                f"HTTP error, retrying (max {max_retries} times): "
                f"return_code: {return_code}, error: {err}, url: {url}",
            )
            await sleep(1000)
            return await http_request(url, options, timeout, max_retries - 1)
        raise HttpError(url, return_code, 0, err)

    headers_end_index = out.index("\r\n\r\n")
    headers = out[:headers_end_index].split("\r\n")
    http_status = int(headers[0].split(" ")[1])

    if http_status == 429:
        for header in headers[1:]:
            name, value = header.split(":", 1)
            if name.lower() == "retry-after":
                retry_after = int(value.strip())
                log(
                    LogLevel.INFO,
                    f"HTTP ratelimit, retrying in {retry_after} seconds, url: {url}",
                )
                await sleep(retry_after * 1000)
                return await http_request(url, options, timeout)

    body = out[headers_end_index + 4 :]

    if http_status >= 400:
        raise HttpError(url, return_code, http_status, body)

    return body


### Slack Classes


class SlackConfigSectionColor:
    def __init__(self, weechat_config: WeeChatConfig):
        self._section = WeeChatSection(weechat_config, "color")

        self.reaction_suffix = WeeChatOption(
            self._section,
            "reaction_suffix",
            "Color to use for the [:wave:(@user)] suffix on messages that have reactions attached to them.",
            WeeChatColor("darkgray"),
        )


class SlackConfigSectionWorkspace:
    def __init__(
        self,
        section: WeeChatSection,
        team: Union[SlackTeam, None],
        parent_config: Union[SlackConfigSectionWorkspace, None],
    ):
        self._section = section
        self._team = team
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

        self.slack_timeout = self._create_option(
            "slack_timeout",
            "timeout (in seconds) for network requests",
            30,
        )

    def _create_option(
        self,
        name: str,
        description: str,
        default_value: WeeChatOptionType,
        min_value: Union[int, None] = None,
        max_value: Union[int, None] = None,
        string_values: Union[str, None] = None,
    ) -> WeeChatOption[WeeChatOptionType]:
        if self._team:
            option_name = f"{self._team.name}.{name}"
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
    data: str, config_file: str, section: str, option_name: str, value: Union[str, None]
) -> int:
    option_split = option_name.split(".", 1)
    if len(option_split) < 2:
        return weechat.WEECHAT_CONFIG_OPTION_SET_ERROR
    workspace_name, name = option_split
    if not workspace_name or not name:
        return weechat.WEECHAT_CONFIG_OPTION_SET_ERROR

    if workspace_name not in workspaces:
        workspaces[workspace_name] = SlackTeam(workspace_name)

    option = getattr(workspaces[workspace_name].config, name, None)
    if option is None:
        return weechat.WEECHAT_CONFIG_OPTION_SET_OPTION_NOT_FOUND
    if not isinstance(option, WeeChatOption):
        return weechat.WEECHAT_CONFIG_OPTION_SET_ERROR

    if value is None or (
        weechat_version < 0x3080000 and value == "" and option.weechat_type != "string"
    ):
        rc = option.value_set_null()
    else:
        rc = option.value_set_as_str(value)
    if rc == weechat.WEECHAT_CONFIG_OPTION_SET_ERROR:
        print_error(f'error creating workspace option "{option_name}"')
    return rc


class SlackConfig:
    def __init__(self):
        self.weechat_config = WeeChatConfig("slack")
        self.color = SlackConfigSectionColor(self.weechat_config)
        self._section_workspace_default = WeeChatSection(
            self.weechat_config, "workspace_default"
        )
        self._section_workspace = WeeChatSection(
            self.weechat_config,
            "workspace",
            callback_read=config_section_workspace_read_cb.__name__,
        )
        self._workspace_default = SlackConfigSectionWorkspace(
            self._section_workspace_default, None, None
        )

    def config_read(self):
        weechat.config_read(self.weechat_config.pointer)

    def create_workspace_config(self, team: SlackTeam):
        if team.name in workspaces:
            raise Exception(
                f"Failed to create workspace config, already exists: {team.name}"
            )
        return SlackConfigSectionWorkspace(
            self._section_workspace, team, self._workspace_default
        )


class SlackApi:
    def __init__(self, team: SlackTeam):
        self.team = team

    def get_request_options(self):
        return {
            "useragent": f"wee_slack {SCRIPT_VERSION}",
            "httpheader": f"Authorization: Bearer {self.team.config.api_token.value}",
            "cookie": self.team.config.api_cookies.value,
        }

    async def fetch(self, method: str, params: Dict[str, Union[str, int]] = {}):
        url = f"https://api.slack.com/api/{method}?{urlencode(params)}"
        response = await http_request(
            url,
            self.get_request_options(),
            self.team.config.slack_timeout.value * 1000,
        )
        return json.loads(response)

    async def fetch_list(
        self,
        method: str,
        list_key: str,
        params: Dict[str, Union[str, int]] = {},
        pages: int = 1,  # negative or 0 means all pages
    ):
        response = await self.fetch(method, params)
        next_cursor = response.get("response_metadata", {}).get("next_cursor")
        if pages != 1 and next_cursor and response["ok"]:
            params["cursor"] = next_cursor
            next_pages = await self.fetch_list(method, list_key, params, pages - 1)
            response[list_key].extend(next_pages[list_key])
            return response
        return response


class SlackTeam:
    def __init__(self, name: str):
        self.name = name
        self.config = config.create_workspace_config(self)
        self.api = SlackApi(self)


class SlackChannelCommonNew:
    def __init__(self, team: SlackTeam, slack_info: SlackConversation):
        self.team = team
        self.api = team.api
        self.id = slack_info["id"]
        # self.fetch_info()

    async def fetch_info(self):
        response = await self.api.fetch("conversations.info", {"channel": self.id})
        print(len(response))


class SlackChannelNew(SlackChannelCommonNew):
    def __init__(self, team: SlackTeam, slack_info: SlackConversationNotIm):
        super().__init__(team, slack_info)
        self.name = slack_info["name"]


class SlackIm(SlackChannelCommonNew):
    def __init__(self, team: SlackTeam, slack_info: SlackConversationIm):
        super().__init__(team, slack_info)
        self.user = slack_info["user"]


async def init():
    print(workspaces)
    if "wee-slack-test" not in workspaces:
        workspaces["wee-slack-test"] = SlackTeam("wee-slack-test")
        workspaces["wee-slack-test"].config.api_token.value = weechat.config_get_plugin(
            "api_token"
        )
        workspaces[
            "wee-slack-test"
        ].config.api_cookies.value = weechat.config_get_plugin("api_cookie")
    team = workspaces["wee-slack-test"]
    print(team)
    print(team.config.slack_timeout.value)
    print(config.color.reaction_suffix.value)


if __name__ == "__main__":
    if weechat.register(
        SCRIPT_NAME,
        SCRIPT_AUTHOR,
        SCRIPT_VERSION,
        SCRIPT_LICENSE,
        SCRIPT_DESC,
        shutdown_cb.__name__,
        "",
    ):
        weechat_version = int(weechat.info_get("version_number", "") or 0)
        workspaces: Dict[str, SlackTeam] = {}
        config = SlackConfig()
        config.config_read()
        create_task(init(), final=True)

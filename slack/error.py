from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Dict, Optional
from uuid import uuid4

from slack.python_compatibility import format_exception_only
from slack.shared import shared

if TYPE_CHECKING:
    from slack_api.slack_common import SlackErrorResponse
    from slack_rtm.slack_rtm_message import SlackRtmMessage

    from slack.slack_workspace import SlackWorkspace


class HttpError(Exception):
    def __init__(
        self,
        url: str,
        options: Dict[str, str],
        return_code: Optional[int],
        http_status_code: Optional[int],
        error: str,
    ):
        super().__init__(
            f"{self.__class__.__name__}: url='{url}', return_code={return_code}, http_status_code={http_status_code}, error='{error}'"
        )
        self.url = url
        self.options = options
        self.return_code = return_code
        self.http_status_code = http_status_code
        self.error = error


class SlackApiError(Exception):
    def __init__(
        self,
        workspace: SlackWorkspace,
        method: str,
        response: SlackErrorResponse,
        request: object = None,
    ):
        super().__init__(
            f"{self.__class__.__name__}: workspace={workspace}, method='{method}', request={request}, response={response}"
        )
        self.workspace = workspace
        self.method = method
        self.request = request
        self.response = response


class SlackRtmError(Exception):
    def __init__(
        self,
        workspace: SlackWorkspace,
        exception: BaseException,
        message_json: SlackRtmMessage,
    ):
        super().__init__(
            f"{self.__class__.__name__}: workspace={workspace}, exception=`{format_exception_only_str(exception)}`"
        )
        super().with_traceback(exception.__traceback__)
        self.workspace = workspace
        self.exception = exception
        self.message_json = message_json


class SlackError(Exception):
    def __init__(
        self, workspace: SlackWorkspace, error: str, data: Optional[object] = None
    ):
        super().__init__(
            f"{self.__class__.__name__}: workspace={workspace}, error={error}"
        )
        self.workspace = workspace
        self.error = error
        self.data = data


@dataclass
class UncaughtError:
    id: str = field(init=False)
    exception: BaseException

    def __post_init__(self):
        self.id = str(uuid4())
        self.time = datetime.now()


def format_exception_only_str(exc: BaseException) -> str:
    return format_exception_only(exc)[-1].strip()


def store_uncaught_error(uncaught_error: UncaughtError) -> None:
    shared.uncaught_errors.append(uncaught_error)


def store_and_format_uncaught_error(uncaught_error: UncaughtError) -> str:
    store_uncaught_error(uncaught_error)
    e = uncaught_error.exception
    stack_msg_command = f"/slack debug error {uncaught_error.id}"
    stack_msg = f"run `{stack_msg_command}` for the stack trace"

    if isinstance(e, HttpError):
        return (
            f"Error calling URL {e.url}: return code: {e.return_code}, "
            f"http status code: {e.http_status_code}, error: {e.error} ({stack_msg})"
        )
    elif isinstance(e, SlackApiError):
        return (
            f"Error from Slack API method {e.method} with request {e.request} for workspace "
            f"{e.workspace.name}: {e.response} ({stack_msg})"
        )
    elif isinstance(e, SlackRtmError):
        return (
            f"Error while handling Slack event of type '{e.message_json['type']}' for workspace "
            f"{e.workspace.name}: {format_exception_only_str(e.exception)} ({stack_msg}, "
            f"run `{stack_msg_command} -data` for the event data)"
        )
    elif isinstance(e, SlackError):
        return (
            f"Error occurred in workspace {e.workspace.name}: {e.error} ({stack_msg})"
        )
    else:
        return f"Unknown error occurred: {format_exception_only_str(e)} ({stack_msg})"


def store_and_format_exception(e: BaseException) -> str:
    uncaught_error = UncaughtError(e)
    return store_and_format_uncaught_error(uncaught_error)

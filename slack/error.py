from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Mapping, Sequence, Union

if TYPE_CHECKING:
    from slack_api.slack_error import SlackErrorResponse

    from slack.slack_workspace import SlackWorkspace


class HttpError(Exception):
    def __init__(
        self,
        url: str,
        options: Dict[str, str],
        return_code: int,
        http_status_code: int,
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
        params: Mapping[
            str, Union[str, int, bool, Sequence[str], Sequence[int], Sequence[bool]]
        ] = {},
    ):
        super().__init__(
            f"{self.__class__.__name__}: workspace={workspace}, method='{method}', params={params}, response={response}"
        )
        self.workspace = workspace
        self.method = method
        self.params = params
        self.response = response


class SlackError(Exception):
    def __init__(self, workspace: SlackWorkspace, error: str):
        super().__init__(
            f"{self.__class__.__name__}: workspace={workspace}, error={error}"
        )
        self.workspace = workspace
        self.error = error


def format_exception(e: BaseException):
    if isinstance(e, HttpError):
        return (
            f"Error calling URL {e.url}: return code: {e.return_code}, "
            f"http status code: {e.http_status_code}, error: {e.error}"
        )
    elif isinstance(e, SlackApiError):
        return (
            f"Error from Slack API method {e.method} with params {e.params} for workspace "
            f"{e.workspace.name}: {e.response}"
        )
    elif isinstance(e, SlackError):
        return f"Error occurred in workspace {e.workspace.name}: {e.error}"
    else:
        return f"Unknown error occurred: {e.__class__.__name__}: {e}"

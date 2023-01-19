from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Union

if TYPE_CHECKING:
    from slack_api.slack_error import SlackErrorResponse

    from slack.slack_workspace import SlackWorkspace


class HttpError(Exception):
    def __init__(self, url: str, return_code: int, http_status_code: int, error: str):
        super().__init__()
        self.url = url
        self.return_code = return_code
        self.http_status_code = http_status_code
        self.error = error


class SlackApiError(Exception):
    def __init__(
        self,
        workspace: SlackWorkspace,
        method: str,
        response: SlackErrorResponse,
        params: Mapping[str, Union[str, int, bool]] = {},
    ):
        super().__init__()
        self.workspace = workspace
        self.method = method
        self.params = params
        self.response = response

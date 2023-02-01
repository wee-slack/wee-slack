from typing import List

from slack_api.slack_common import SlackErrorResponse
from slack_api.slack_users_info import SlackUserInfo
from typing_extensions import Literal, TypedDict

class SlackUsersSearchSuccessResponse(TypedDict):
    ok: Literal[True]
    results: List[SlackUserInfo]
    presence_active_ids: List[str]

SlackUsersSearchResponse = SlackUsersSearchSuccessResponse | SlackErrorResponse

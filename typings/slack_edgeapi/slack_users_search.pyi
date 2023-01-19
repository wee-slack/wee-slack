from typing import List, Literal, TypedDict

from slack_api.slack_error import SlackErrorResponse
from slack_api.slack_users_info import SlackUserInfo

class SlackUsersSearchSuccessResponse(TypedDict):
    ok: Literal[True]
    results: List[SlackUserInfo]
    presence_active_ids: List[str]

SlackUsersSearchResponse = SlackUsersSearchSuccessResponse | SlackErrorResponse

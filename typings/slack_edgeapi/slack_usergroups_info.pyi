from typing import List

from slack_api.slack_common import SlackErrorResponse
from slack_api.slack_usergroups_info import SlackUsergroupInfo
from typing_extensions import Literal, NotRequired, TypedDict

class SlackEdgeUsergroupsInfoSuccessResponse(TypedDict):
    ok: Literal[True]
    failed_ids: NotRequired[List[str]]
    results: List[SlackUsergroupInfo]

SlackEdgeUsergroupsInfoResponse = (
    SlackEdgeUsergroupsInfoSuccessResponse | SlackErrorResponse
)

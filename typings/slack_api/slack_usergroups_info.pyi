from typing import List

from slack_api.slack_common import SlackErrorResponse
from typing_extensions import Literal, NotRequired, TypedDict, final

class SlackUsergroupPrefs(TypedDict):
    channels: List[str]
    groups: List[str]

class SlackUsergroupInfoCommon(TypedDict):
    id: str
    team_id: str
    is_usergroup: bool
    is_subteam: bool
    name: str
    description: str
    handle: str
    is_external: bool
    date_create: int
    date_update: int
    date_delete: int
    auto_type: None
    auto_provision: bool
    enterprise_subteam_id: str
    created_by: str
    updated_by: str
    deleted_by: None
    prefs: SlackUsergroupPrefs
    user_count: int
    channel_count: int

class SlackUsergroupInfo(SlackUsergroupInfoCommon):
    users: NotRequired[List[str]]

@final
class SlackUsergroupsInfoSuccessResponse(TypedDict):
    ok: Literal[True]
    usergroups: List[SlackUsergroupInfo]

SlackUsergroupsInfoResponse = SlackUsergroupsInfoSuccessResponse | SlackErrorResponse

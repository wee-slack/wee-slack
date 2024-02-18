from __future__ import annotations

from typing import Generic, List, TypeVar

from slack_api.slack_common import SlackErrorResponse
from slack_api.slack_profile import SlackProfileBot, SlackProfilePerson
from typing_extensions import Literal, NotRequired, TypedDict, final

T = TypeVar("T")

@final
class SlackEnterpriseUser(TypedDict):
    id: str
    enterprise_id: str
    enterprise_name: str
    is_admin: bool
    is_owner: bool
    is_primary_owner: bool
    teams: List[str]

class SlackUserInfoCommon(TypedDict):
    id: str
    team_id: NotRequired[str]
    name: str
    deleted: NotRequired[bool]
    color: str
    real_name: NotRequired[str]
    tz: NotRequired[str]
    tz_label: NotRequired[str]
    tz_offset: NotRequired[int]
    is_admin: NotRequired[bool]
    is_owner: NotRequired[bool]
    is_primary_owner: NotRequired[bool]
    is_restricted: NotRequired[bool]
    is_ultra_restricted: NotRequired[bool]
    is_app_user: bool
    updated: int
    is_email_confirmed: NotRequired[bool]
    who_can_share_contact_card: str
    enterprise_user: NotRequired[SlackEnterpriseUser]
    enterprise_id: NotRequired[str]
    presence: NotRequired[Literal["active"]]

@final
class SlackUserInfoPerson(SlackUserInfoCommon):
    profile: SlackProfilePerson
    is_bot: Literal[False]
    is_stranger: NotRequired[bool]
    has_2fa: NotRequired[bool]

@final
class SlackUserInfoBot(SlackUserInfoCommon):
    profile: SlackProfileBot
    is_bot: Literal[True]
    is_workflow_bot: NotRequired[bool]

SlackUserInfo = SlackUserInfoPerson | SlackUserInfoBot

@final
class SlackUserInfoSuccessResponse(TypedDict, Generic[T]):
    ok: Literal[True]
    user: T

SlackUserInfoPersonResponse = (
    SlackUserInfoSuccessResponse[SlackUserInfoPerson] | SlackErrorResponse
)
SlackUserInfoBotResponse = (
    SlackUserInfoSuccessResponse[SlackUserInfoBot] | SlackErrorResponse
)
SlackUserInfoResponse = SlackUserInfoSuccessResponse[SlackUserInfo] | SlackErrorResponse

@final
class SlackUsersInfoSuccessResponse(TypedDict, Generic[T]):
    ok: Literal[True]
    users: List[T]

SlackUsersInfoPersonResponse = (
    SlackUsersInfoSuccessResponse[SlackUserInfoPerson] | SlackErrorResponse
)
SlackUsersInfoBotResponse = (
    SlackUsersInfoSuccessResponse[SlackUserInfoBot] | SlackErrorResponse
)
SlackUsersInfoResponse = (
    SlackUsersInfoSuccessResponse[SlackUserInfo] | SlackErrorResponse
)

from __future__ import annotations

from slack_api.slack_common import SlackErrorResponse
from typing_extensions import Literal, NotRequired, TypedDict, final

@final
class SlackTeamInfoIcon(TypedDict):
    image_default: bool
    image_34: str
    image_44: str
    image_68: str
    image_88: str
    image_102: str
    image_230: str
    image_132: str

@final
class SlackTeamInfo(TypedDict):
    id: str
    name: str
    url: str
    domain: str
    email_domain: str
    icon: SlackTeamInfoIcon
    avatar_base_url: str
    is_verified: bool

    # For enterprise grid
    public_url: NotRequired[str]
    discoverable: NotRequired[str]
    # sso_provider
    # pay_prod_cur
    locale: NotRequired[str]
    enterprise_id: NotRequired[str]
    enterprise_name: NotRequired[str]
    enterprise_domain: NotRequired[str]

@final
class SlackTeamInfoSuccessResponse(TypedDict):
    ok: Literal[True]
    team: SlackTeamInfo

SlackTeamInfoResponse = SlackTeamInfoSuccessResponse | SlackErrorResponse

from __future__ import annotations

from typing import Dict, Generic, List, Literal, TypedDict, TypeVar, final

T = TypeVar("T")

class SlackProfileCommon(TypedDict):
    title: str
    phone: str
    skype: str
    real_name: str
    real_name_normalized: str
    display_name: str
    display_name_normalized: str
    fields: Dict  # pyright: ignore [reportMissingTypeArgument]
    status_text: str
    status_emoji: str
    status_emoji_display_info: List  # pyright: ignore [reportMissingTypeArgument]
    status_expiration: int
    avatar_hash: str
    image_24: str
    image_32: str
    image_48: str
    image_72: str
    image_192: str
    image_512: str
    status_text_canonical: str
    team: str

@final
class SlackProfilePerson(SlackProfileCommon):
    email: str

@final
class SlackProfileBot(SlackProfileCommon):
    api_app_id: str
    always_active: bool
    image_original: str
    is_custom_image: bool
    bot_id: str
    image_1024: str

class SlackUsersInfoCommon(TypedDict):
    id: str
    team_id: str
    name: str
    deleted: bool
    color: str
    real_name: str
    tz: str
    tz_label: str
    tz_offset: int
    is_admin: bool
    is_owner: bool
    is_primary_owner: bool
    is_restricted: bool
    is_ultra_restricted: bool
    is_app_user: bool
    updated: int
    is_email_confirmed: bool
    who_can_share_contact_card: str

@final
class SlackUsersInfoPerson(SlackUsersInfoCommon):
    profile: SlackProfilePerson
    is_bot: Literal[False]
    has_2fa: bool

@final
class SlackUsersInfoBot(SlackUsersInfoCommon):
    profile: SlackProfileBot
    is_bot: Literal[True]

SlackUsersInfo = SlackUsersInfoPerson | SlackUsersInfoBot

@final
class SlackUsersInfoErrorResponse(TypedDict):
    ok: Literal[False]
    error: str

@final
class SlackUsersInfoSuccessResponse(TypedDict, Generic[T]):
    ok: Literal[True]
    user: T

SlackUsersInfoPersonResponse = (
    SlackUsersInfoSuccessResponse[SlackUsersInfoPerson] | SlackUsersInfoErrorResponse
)
SlackUsersInfoBotResponse = (
    SlackUsersInfoSuccessResponse[SlackUsersInfoBot] | SlackUsersInfoErrorResponse
)
SlackUsersInfoResponse = (
    SlackUsersInfoSuccessResponse[SlackUsersInfo] | SlackUsersInfoErrorResponse
)

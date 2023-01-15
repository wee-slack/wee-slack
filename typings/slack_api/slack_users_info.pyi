from __future__ import annotations

from typing import Dict, Generic, List, Literal, Optional, TypedDict, TypeVar, final

from typing_extensions import NotRequired

T = TypeVar("T")

class SlackProfileCommon(TypedDict):
    title: NotRequired[Optional[str]]
    phone: NotRequired[Optional[str]]
    skype: NotRequired[Optional[str]]
    real_name: NotRequired[Optional[str]]
    real_name_normalized: NotRequired[Optional[str]]
    display_name: NotRequired[Optional[str]]
    display_name_normalized: NotRequired[Optional[str]]
    # fields: NotRequired[Optional[Dict]]  # pyright: ignore [reportMissingTypeArgument]
    status_text: NotRequired[Optional[str]]
    status_emoji: NotRequired[Optional[str]]
    # status_emoji_display_info: NotRequired[
    #     Optional[List]  # pyright: ignore [reportMissingTypeArgument]
    # ]
    status_expiration: NotRequired[Optional[int]]
    avatar_hash: NotRequired[Optional[str]]
    image_24: str
    image_32: str
    image_48: str
    image_72: str
    image_192: str
    image_512: str
    status_text_canonical: NotRequired[Optional[str]]
    team: str

@final
class SlackProfilePerson(SlackProfileCommon):
    email: NotRequired[Optional[str]]

@final
class SlackProfileBot(SlackProfileCommon):
    api_app_id: NotRequired[Optional[str]]
    always_active: NotRequired[Optional[bool]]
    image_original: str
    is_custom_image: NotRequired[Optional[bool]]
    bot_id: NotRequired[Optional[str]]
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

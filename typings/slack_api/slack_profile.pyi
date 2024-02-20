from __future__ import annotations

from typing import Dict, List, Optional

from slack_api.slack_common import SlackErrorResponse
from typing_extensions import Literal, NotRequired, TypedDict, final

@final
class SlackProfileField(TypedDict):
    value: str
    alt: str

@final
class SlackProfileStatusEmojiDisplayInfo(TypedDict):
    emoji_name: str
    display_url: str
    unicode: str

class SlackProfileCommon(TypedDict):
    title: NotRequired[Optional[str]]
    phone: NotRequired[Optional[str]]
    skype: NotRequired[Optional[str]]
    first_name: NotRequired[Optional[str]]
    last_name: NotRequired[Optional[str]]
    real_name: NotRequired[Optional[str]]
    real_name_normalized: NotRequired[Optional[str]]
    display_name: NotRequired[Optional[str]]
    display_name_normalized: NotRequired[Optional[str]]
    fields: NotRequired[Optional[Dict[str, SlackProfileField]]]
    status_text: NotRequired[Optional[str]]
    status_emoji: NotRequired[Optional[str]]
    status_emoji_display_info: NotRequired[
        Optional[List[SlackProfileStatusEmojiDisplayInfo]]
    ]
    status_expiration: NotRequired[Optional[int]]
    avatar_hash: NotRequired[Optional[str]]
    image_original: NotRequired[str]
    is_custom_image: NotRequired[Optional[bool]]
    huddle_state: NotRequired[Optional[str]]
    huddle_state_expiration_ts: NotRequired[Optional[int]]
    image_24: NotRequired[str]
    image_32: NotRequired[str]
    image_48: NotRequired[str]
    image_72: NotRequired[str]
    image_192: NotRequired[str]
    image_512: NotRequired[str]
    image_1024: NotRequired[str]
    status_text_canonical: NotRequired[Optional[str]]
    team: str

@final
class SlackProfilePerson(SlackProfileCommon):
    email: NotRequired[Optional[str]]

@final
class SlackProfileBot(SlackProfileCommon):
    api_app_id: NotRequired[Optional[str]]
    always_active: NotRequired[Optional[bool]]
    bot_id: NotRequired[Optional[str]]

SlackProfile = SlackProfilePerson | SlackProfileBot

@final
class SlackSetProfile(TypedDict):
    display_name: NotRequired[Optional[str]]
    email: NotRequired[Optional[str]]
    first_name: NotRequired[Optional[str]]
    last_name: NotRequired[Optional[str]]
    phone: NotRequired[Optional[str]]
    pronouns: NotRequired[Optional[str]]
    real_name: NotRequired[Optional[str]]
    start_date: NotRequired[Optional[str]]
    title: NotRequired[Optional[str]]
    status_emoji: NotRequired[Optional[str]]
    status_expiration: NotRequired[Optional[int]]
    status_text: NotRequired[Optional[str]]

@final
class SlackUsersProfileSetSuccessResponse(TypedDict):
    ok: Literal[True]
    profile: SlackProfilePerson

SlackUsersProfileSetResponse = SlackUsersProfileSetSuccessResponse | SlackErrorResponse

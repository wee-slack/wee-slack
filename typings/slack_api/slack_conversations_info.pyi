from __future__ import annotations

from typing import Generic, List, TypeVar

from slack_api.slack_common import SlackErrorResponse
from slack_api.slack_conversations_history import SlackMessage
from typing_extensions import Literal, NotRequired, TypedDict, final

T = TypeVar("T")

@final
class SlackTopic(TypedDict):
    value: str
    creator: str
    last_set: int

@final
class SlackPurpose(TypedDict):
    value: str
    creator: str
    last_set: int

class SlackConversationsInfoCommon(TypedDict):
    id: str
    created: int
    is_archived: bool
    is_org_shared: bool
    context_team_id: str
    updated: int
    last_read: NotRequired[str]

class SlackConversationsInfoCommonNotIm(SlackConversationsInfoCommon):
    name: str
    is_channel: bool
    is_group: bool
    is_im: Literal[False]
    is_general: bool
    unlinked: int
    name_normalized: str
    is_shared: bool
    is_pending_ext_shared: bool
    pending_shared: List[str]
    parent_conversation: None
    creator: str
    is_ext_shared: bool
    shared_team_ids: List[str]
    pending_connected_team_ids: List[str]
    is_member: bool
    topic: SlackTopic
    purpose: SlackPurpose

@final
class SlackConversationsInfoPublic(SlackConversationsInfoCommonNotIm):
    is_mpim: Literal[False]
    is_private: Literal[False]
    previous_names: List[str]  # TODO: Check if private and mpim has this

@final
class SlackConversationsInfoPrivate(SlackConversationsInfoCommonNotIm):
    is_mpim: Literal[False]
    is_private: Literal[True]
    is_open: bool

@final
class SlackConversationsInfoMpim(SlackConversationsInfoCommonNotIm):
    is_mpim: Literal[True]
    is_private: Literal[True]
    is_open: bool

@final
class SlackConversationsInfoIm(SlackConversationsInfoCommon):
    is_im: Literal[True]
    user: str
    latest: SlackMessage
    unread_count: int
    unread_count_display: int
    is_open: bool
    priority: int
    topic: NotRequired[SlackTopic]

SlackConversationsInfoNotIm = (
    SlackConversationsInfoPublic
    | SlackConversationsInfoPrivate
    | SlackConversationsInfoMpim
)
SlackConversationsInfo = SlackConversationsInfoNotIm | SlackConversationsInfoIm

@final
class SlackConversationsInfoSuccessResponse(TypedDict, Generic[T]):
    ok: Literal[True]
    channel: T

SlackConversationsInfoPublicResponse = (
    SlackConversationsInfoSuccessResponse[SlackConversationsInfoPublic]
    | SlackErrorResponse
)
SlackConversationsInfoPrivateResponse = (
    SlackConversationsInfoSuccessResponse[SlackConversationsInfoPrivate]
    | SlackErrorResponse
)
SlackConversationsInfoMpimResponse = (
    SlackConversationsInfoSuccessResponse[SlackConversationsInfoMpim]
    | SlackErrorResponse
)
SlackConversationsInfoImResponse = (
    SlackConversationsInfoSuccessResponse[SlackConversationsInfoIm] | SlackErrorResponse
)
SlackConversationsInfoNotImResponse = (
    SlackConversationsInfoSuccessResponse[SlackConversationsInfoNotIm]
    | SlackErrorResponse
)
SlackConversationsInfoResponse = (
    SlackConversationsInfoSuccessResponse[SlackConversationsInfo] | SlackErrorResponse
)

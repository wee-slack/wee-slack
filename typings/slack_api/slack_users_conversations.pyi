from __future__ import annotations

from typing import Generic, List

from slack_api.slack_error import SlackErrorResponse
from slack_api.slack_common import SlackResponseMetadata
from typing_extensions import Literal, TypedDict, TypeVar, final

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

class SlackUsersConversationsCommon(TypedDict):
    id: str
    created: int
    is_archived: bool
    is_org_shared: bool
    context_team_id: str
    updated: int

class SlackUsersConversationsCommonNotIm(SlackUsersConversationsCommon):
    name: str
    is_channel: bool
    is_group: bool
    is_im: Literal[False]
    is_general: bool
    unlinked: int
    name_normalized: str
    is_shared: bool
    is_pending_ext_shared: bool
    pending_shared: List  # pyright: ignore [reportMissingTypeArgument]
    parent_conversation: None
    creator: str
    is_ext_shared: bool
    shared_team_ids: List[str]
    pending_connected_team_ids: List  # pyright: ignore [reportMissingTypeArgument]
    topic: SlackTopic
    purpose: SlackPurpose

@final
class SlackUsersConversationsPublic(SlackUsersConversationsCommonNotIm):
    is_mpim: Literal[False]
    is_private: Literal[False]
    previous_names: List[str]  # TODO: Check if private and mpim has this

@final
class SlackUsersConversationsPrivate(SlackUsersConversationsCommonNotIm):
    is_mpim: Literal[False]
    is_private: Literal[True]

@final
class SlackUsersConversationsMpim(SlackUsersConversationsCommonNotIm):
    is_mpim: Literal[True]
    is_private: Literal[True]

@final
class SlackUsersConversationsIm(SlackUsersConversationsCommon):
    is_im: Literal[True]
    user: str
    is_user_deleted: bool
    priority: int

SlackUsersConversationsNotIm = (
    SlackUsersConversationsPublic
    | SlackUsersConversationsPrivate
    | SlackUsersConversationsMpim
)
SlackUsersConversations = SlackUsersConversationsNotIm | SlackUsersConversationsIm

@final
class SlackUsersConversationsSuccessResponse(TypedDict, Generic[T]):
    ok: Literal[True]
    channels: List[T]
    response_metadata: SlackResponseMetadata

SlackUsersConversationsPublicResponse = (
    SlackUsersConversationsSuccessResponse[SlackUsersConversationsPublic]
    | SlackErrorResponse
)
SlackUsersConversationsPrivateResponse = (
    SlackUsersConversationsSuccessResponse[SlackUsersConversationsPrivate]
    | SlackErrorResponse
)
SlackUsersConversationsMpimResponse = (
    SlackUsersConversationsSuccessResponse[SlackUsersConversationsMpim]
    | SlackErrorResponse
)
SlackUsersConversationsImResponse = (
    SlackUsersConversationsSuccessResponse[SlackUsersConversationsIm]
    | SlackErrorResponse
)
SlackUsersConversationsNotImResponse = (
    SlackUsersConversationsSuccessResponse[SlackUsersConversationsNotIm]
    | SlackErrorResponse
)
SlackUsersConversationsResponse = (
    SlackUsersConversationsSuccessResponse[SlackUsersConversations] | SlackErrorResponse
)

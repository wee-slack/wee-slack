from __future__ import annotations

from typing import List, Literal, TypedDict, final

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

@final
class SlackBlockElement(TypedDict):
    type: str
    text: str

@final
class SlackBlockElementParent(TypedDict):
    type: str
    elements: List[SlackBlockElement]

@final
class SlackBlock(TypedDict):
    type: str
    block_id: str
    elements: List[SlackBlockElementParent]

@final
class SlackLatest(TypedDict):
    client_msg_id: str
    type: str
    text: str
    user: str
    ts: str
    blocks: List[SlackBlock]
    team: str

class SlackConversationInfoCommon(TypedDict):
    id: str
    created: int
    is_archived: bool
    is_org_shared: bool
    context_team_id: str
    last_read: str

class SlackConversationInfoCommonNotIm(SlackConversationInfoCommon):
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
    is_member: bool
    topic: SlackTopic
    purpose: SlackPurpose

@final
class SlackConversationInfoPublic(SlackConversationInfoCommonNotIm):
    is_mpim: Literal[False]
    is_private: Literal[False]
    previous_names: List[str]  # TODO: Check if private and mpim has this

@final
class SlackConversationInfoPrivate(SlackConversationInfoCommonNotIm):
    is_mpim: Literal[False]
    is_private: Literal[True]
    is_open: bool

@final
class SlackConversationInfoMpim(SlackConversationInfoCommonNotIm):
    is_mpim: Literal[True]
    is_private: Literal[True]
    is_open: bool

@final
class SlackConversationInfoIm(SlackConversationInfoCommon):
    is_im: Literal[True]
    user: str
    latest: SlackLatest
    unread_count: int
    unread_count_display: int
    is_open: bool
    priority: int

SlackConversationInfoNotIm = (
    SlackConversationInfoPublic
    | SlackConversationInfoPrivate
    | SlackConversationInfoMpim
)
SlackConversationInfo = SlackConversationInfoNotIm | SlackConversationInfoIm

@final
class SlackConversationInfoErrorResponse(TypedDict):
    ok: Literal[False]
    error: str

@final
class SlackConversationInfoPublicSuccessResponse(TypedDict):
    ok: Literal[True]
    channel: SlackConversationInfoPublic

@final
class SlackConversationInfoPrivateSuccessResponse(TypedDict):
    ok: Literal[True]
    channel: SlackConversationInfoPrivate

@final
class SlackConversationInfoMpimSuccessResponse(TypedDict):
    ok: Literal[True]
    channel: SlackConversationInfoMpim

@final
class SlackConversationInfoImSuccessResponse(TypedDict):
    ok: Literal[True]
    channel: SlackConversationInfoIm

@final
class SlackConversationInfoNotImSuccessResponse(TypedDict):
    ok: Literal[True]
    channel: SlackConversationInfoNotIm

@final
class SlackConversationInfoSuccessResponse(TypedDict):
    ok: Literal[True]
    channel: SlackConversationInfo

SlackConversationInfoPublicResponse = (
    SlackConversationInfoPublicSuccessResponse | SlackConversationInfoErrorResponse
)
SlackConversationInfoPrivateResponse = (
    SlackConversationInfoPrivateSuccessResponse | SlackConversationInfoErrorResponse
)
SlackConversationInfoMpimResponse = (
    SlackConversationInfoMpimSuccessResponse | SlackConversationInfoErrorResponse
)
SlackConversationInfoImResponse = (
    SlackConversationInfoImSuccessResponse | SlackConversationInfoErrorResponse
)
SlackConversationInfoNotImResponse = (
    SlackConversationInfoNotImSuccessResponse | SlackConversationInfoErrorResponse
)
SlackConversationInfoResponse = (
    SlackConversationInfoSuccessResponse | SlackConversationInfoErrorResponse
)

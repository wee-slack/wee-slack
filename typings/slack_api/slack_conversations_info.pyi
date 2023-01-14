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

class SlackConversationsInfoCommon(TypedDict):
    id: str
    created: int
    is_archived: bool
    is_org_shared: bool
    context_team_id: str
    last_read: str

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
    latest: SlackLatest
    unread_count: int
    unread_count_display: int
    is_open: bool
    priority: int

SlackConversationsInfoNotIm = (
    SlackConversationsInfoPublic
    | SlackConversationsInfoPrivate
    | SlackConversationsInfoMpim
)
SlackConversationsInfo = SlackConversationsInfoNotIm | SlackConversationsInfoIm

@final
class SlackConversationsInfoErrorResponse(TypedDict):
    ok: Literal[False]
    error: str

@final
class SlackConversationsInfoPublicSuccessResponse(TypedDict):
    ok: Literal[True]
    channel: SlackConversationsInfoPublic

@final
class SlackConversationsInfoPrivateSuccessResponse(TypedDict):
    ok: Literal[True]
    channel: SlackConversationsInfoPrivate

@final
class SlackConversationsInfoMpimSuccessResponse(TypedDict):
    ok: Literal[True]
    channel: SlackConversationsInfoMpim

@final
class SlackConversationsInfoImSuccessResponse(TypedDict):
    ok: Literal[True]
    channel: SlackConversationsInfoIm

@final
class SlackConversationsInfoNotImSuccessResponse(TypedDict):
    ok: Literal[True]
    channel: SlackConversationsInfoNotIm

@final
class SlackConversationsInfoSuccessResponse(TypedDict):
    ok: Literal[True]
    channel: SlackConversationsInfo

SlackConversationsInfoPublicResponse = (
    SlackConversationsInfoPublicSuccessResponse | SlackConversationsInfoErrorResponse
)
SlackConversationsInfoPrivateResponse = (
    SlackConversationsInfoPrivateSuccessResponse | SlackConversationsInfoErrorResponse
)
SlackConversationsInfoMpimResponse = (
    SlackConversationsInfoMpimSuccessResponse | SlackConversationsInfoErrorResponse
)
SlackConversationsInfoImResponse = (
    SlackConversationsInfoImSuccessResponse | SlackConversationsInfoErrorResponse
)
SlackConversationsInfoNotImResponse = (
    SlackConversationsInfoNotImSuccessResponse | SlackConversationsInfoErrorResponse
)
SlackConversationsInfoResponse = (
    SlackConversationsInfoSuccessResponse | SlackConversationsInfoErrorResponse
)

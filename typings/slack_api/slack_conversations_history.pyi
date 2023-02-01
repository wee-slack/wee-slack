from __future__ import annotations

from typing import Dict, List

from slack_api.slack_common import SlackErrorResponse
from typing_extensions import Literal, NotRequired, TypedDict, final

@final
class SlackMessageBlockElement(TypedDict):
    type: str
    url: NotRequired[str]
    text: str

@final
class SlackMessageBlockElementParent(TypedDict):
    type: str
    elements: List[SlackMessageBlockElement]

@final
class SlackMessageBlock(TypedDict):
    type: str
    block_id: str
    elements: List[SlackMessageBlockElementParent]

@final
class SlackMessageAttachment(TypedDict):
    from_url: str
    image_url: str
    image_width: int
    image_height: int
    image_bytes: int
    service_icon: str
    id: int
    original_url: str
    fallback: str
    text: str
    title: str
    title_link: str
    service_name: str

@final
class SlackMessageReaction(TypedDict):
    name: str
    users: List[str]
    count: int

@final
class SlackMessageFile(TypedDict):
    id: str
    created: int
    timestamp: int
    name: str
    title: str
    mimetype: str
    filetype: str
    pretty_type: str
    user: str
    user_team: str
    editable: bool
    size: int
    mode: str
    is_external: bool
    external_type: str
    is_public: bool
    public_url_shared: bool
    display_as_bot: bool
    username: str
    url_private: str
    url_private_download: str
    permalink: str
    permalink_public: str
    preview: str
    editor: None
    last_editor: str
    non_owner_editable: bool
    updated: int
    is_starred: bool
    has_rich_preview: bool
    file_access: str
    media_progress: None

class SlackMessageCommon(TypedDict):
    type: Literal["message"]
    text: str
    ts: str
    reactions: NotRequired[List[SlackMessageReaction]]

class SlackMessageStandardCommon(SlackMessageCommon):
    client_msg_id: NotRequired[str]
    user: str
    blocks: List[SlackMessageBlock]
    attachments: NotRequired[List[SlackMessageAttachment]]
    team: str

@final
class SlackMessageStandard(SlackMessageStandardCommon):
    pass

class SlackMessageThreadParentCommon(SlackMessageStandardCommon):
    thread_ts: str
    reply_count: int
    reply_users_count: int
    latest_reply: str
    reply_users: List[str]
    is_locked: bool

@final
class SlackMessageThreadParentNotSubscribed(SlackMessageThreadParentCommon):
    subscribed: Literal[False]

@final
class SlackMessageThreadParentSubscribed(SlackMessageThreadParentCommon):
    subscribed: Literal[True]
    last_read: str

@final
class SlackMessageWithFiles(SlackMessageCommon):
    user: str
    files: List[SlackMessageFile]
    upload: bool
    display_as_bot: bool

# TODO: Add other subtypes
@final
class SlackMessageSubtypeBotMessage(SlackMessageCommon):
    subtype: Literal["bot_message"]
    bot_id: str
    username: NotRequired[str]
    icons: NotRequired[Dict[str, str]]

@final
class SlackMessageSubtypeBotRemove(SlackMessageCommon):
    subtype: Literal["bot_remove"]
    user: str
    bot_id: str
    bot_link: str

@final
class SlackMessageSubtypeBotAdd(SlackMessageCommon):
    subtype: Literal["bot_add"]
    user: str
    bot_id: str
    bot_link: str

SlackMessage = (
    SlackMessageStandard
    | SlackMessageThreadParentNotSubscribed
    | SlackMessageThreadParentSubscribed
    | SlackMessageWithFiles
    | SlackMessageSubtypeBotMessage
    | SlackMessageSubtypeBotRemove
    | SlackMessageSubtypeBotAdd
)

@final
class SlackConversationsHistorySuccessResponse(TypedDict):
    ok: Literal[True]
    messages: List[SlackMessage]
    has_more: bool
    is_limited: NotRequired[bool]
    pin_count: int
    channel_actions_ts: None
    channel_actions_count: int

SlackConversationsHistoryResponse = (
    SlackConversationsHistorySuccessResponse | SlackErrorResponse
)

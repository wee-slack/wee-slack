from __future__ import annotations

from typing import Dict, List

from slack_api.slack_common import SlackErrorResponse
from slack_rtm.slack_rtm_message import SlackMessageRtm
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
class SlackMessageEdited(TypedDict):
    user: str
    ts: str

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
    edited: SlackMessageEdited

@final
class SlackMessageStandardFinal(SlackMessageStandardCommon):
    pass

class SlackMessageThreadParentCommon(SlackMessageStandardCommon):
    thread_ts: str
    reply_count: int
    reply_users_count: int
    latest_reply: str
    reply_users: List[str]
    is_locked: bool

class SlackMessageThreadParentNotSubscribed(SlackMessageThreadParentCommon):
    subscribed: Literal[False]

@final
class SlackMessageThreadParentNotSubscribedFinal(SlackMessageThreadParentNotSubscribed):
    pass

class SlackMessageThreadParentSubscribed(SlackMessageThreadParentCommon):
    subscribed: Literal[True]
    last_read: str

@final
class SlackMessageThreadParentSubscribedFinal(SlackMessageThreadParentSubscribed):
    pass

class SlackMessageWithFiles(SlackMessageCommon):
    user: str
    files: List[SlackMessageFile]
    upload: bool
    display_as_bot: bool

@final
class SlackMessageWithFilesFinal(SlackMessageWithFiles):
    pass

# TODO: Add other subtypes
class SlackMessageSubtypeBotMessage(SlackMessageCommon):
    subtype: Literal["bot_message"]
    bot_id: str
    username: NotRequired[str]
    icons: NotRequired[Dict[str, str]]

@final
class SlackMessageSubtypeBotMessageFinal(SlackMessageSubtypeBotMessage):
    pass

class SlackMessageSubtypeBotRemove(SlackMessageCommon):
    subtype: Literal["bot_remove"]
    user: str
    bot_id: str
    bot_link: str

@final
class SlackMessageSubtypeBotRemoveFinal(SlackMessageSubtypeBotRemove):
    pass

class SlackMessageSubtypeBotAdd(SlackMessageCommon):
    subtype: Literal["bot_add"]
    user: str
    bot_id: str
    bot_link: str

@final
class SlackMessageSubtypeBotAddFinal(SlackMessageSubtypeBotAdd):
    pass

class SlackMessageSubtypeChannelJoin(SlackMessageCommon):
    subtype: Literal["channel_join", "group_join"]
    user: str
    inviter: NotRequired[str]

@final
class SlackMessageSubtypeChannelJoinFinal(SlackMessageSubtypeChannelJoin):
    pass

class SlackMessageSubtypeChannelLeave(SlackMessageCommon):
    subtype: Literal["channel_leave", "group_leave"]
    user: str

@final
class SlackMessageSubtypeChannelLeaveFinal(SlackMessageSubtypeChannelLeave):
    pass

SlackMessage = (
    SlackMessageStandardFinal
    | SlackMessageThreadParentNotSubscribedFinal
    | SlackMessageThreadParentSubscribedFinal
    | SlackMessageWithFilesFinal
    | SlackMessageSubtypeBotMessageFinal
    | SlackMessageSubtypeBotRemoveFinal
    | SlackMessageSubtypeBotAddFinal
    | SlackMessageSubtypeChannelJoinFinal
    | SlackMessageSubtypeChannelLeaveFinal
    | SlackMessageRtm
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

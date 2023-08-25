from __future__ import annotations

from typing import Dict, List

from slack_api.slack_common import SlackErrorResponse
from slack_rtm.slack_rtm_message import SlackMessageRtm
from typing_extensions import Literal, NotRequired, TypedDict, final

@final
class SlackMessageBlockRichTextElementTextStyle(TypedDict):
    bold: bool
    italic: bool
    strike: bool
    code: bool

@final
class SlackMessageBlockRichTextElementText(TypedDict):
    type: Literal["text"]
    text: str
    style: NotRequired[SlackMessageBlockRichTextElementTextStyle]

@final
class SlackMessageBlockRichTextElementLink(TypedDict):
    type: Literal["link"]
    url: str
    text: NotRequired[str]
    style: NotRequired[SlackMessageBlockRichTextElementTextStyle]

@final
class SlackMessageBlockRichTextElementEmoji(TypedDict):
    type: Literal["emoji"]
    name: str
    unicode: str
    skin_tone: int

@final
class SlackMessageBlockRichTextElementChannel(TypedDict):
    type: Literal["channel"]
    channel_id: str

@final
class SlackMessageBlockRichTextElementUser(TypedDict):
    type: Literal["user"]
    user_id: str

@final
class SlackMessageBlockRichTextElementUsergroup(TypedDict):
    type: Literal["usergroup"]
    usergroup_id: str

@final
class SlackMessageBlockRichTextElementBroadcast(TypedDict):
    type: Literal["broadcast"]
    range: Literal["channel", "here"]

SlackMessageBlockRichTextElement = (
    SlackMessageBlockRichTextElementText
    | SlackMessageBlockRichTextElementLink
    | SlackMessageBlockRichTextElementEmoji
    | SlackMessageBlockRichTextElementChannel
    | SlackMessageBlockRichTextElementUser
    | SlackMessageBlockRichTextElementUsergroup
    | SlackMessageBlockRichTextElementBroadcast
)

@final
class SlackMessageBlockRichTextSection(TypedDict):
    type: Literal["rich_text_section"]
    elements: List[SlackMessageBlockRichTextElement]

@final
class SlackMessageBlockRichTextPreformatted(TypedDict):
    type: Literal["rich_text_preformatted"]
    elements: List[
        SlackMessageBlockRichTextElementText | SlackMessageBlockRichTextElementLink
    ]

@final
class SlackMessageBlockRichTextQuote(TypedDict):
    type: Literal["rich_text_quote"]
    elements: List[SlackMessageBlockRichTextElement]

@final
class SlackMessageBlockRichTextList(TypedDict):
    type: Literal["rich_text_list"]
    elements: List[SlackMessageBlockRichTextSection]
    style: Literal["ordered", "bullet"]
    indent: int
    offset: int
    border: int

@final
class SlackMessageBlockRichText(TypedDict):
    type: Literal["rich_text"]
    block_id: NotRequired[str]
    elements: List[
        SlackMessageBlockRichTextSection
        | SlackMessageBlockRichTextPreformatted
        | SlackMessageBlockRichTextQuote
        | SlackMessageBlockRichTextList
    ]

@final
class SlackMessageBlockCallV1(TypedDict):
    id: str
    app_id: str
    app_icon_urls: object
    date_start: int
    active_participants: List[str]
    all_participants: List[str]
    display_id: str
    join_url: str
    desktop_app_join_url: str
    name: str
    created_by: str
    date_end: int
    channels: List[str]
    is_dm_call: bool
    was_rejected: bool
    was_missed: bool
    was_accepted: bool
    has_ended: bool

@final
class SlackMessageBlockCallCall(TypedDict):
    v1: SlackMessageBlockCallV1
    media_backend_type: str

@final
class SlackMessageBlockCall(TypedDict):
    type: Literal["call"]
    block_id: NotRequired[str]
    call_id: str
    api_decoration_available: bool
    call: SlackMessageBlockCallCall

@final
class SlackMessageBlockCompositionPlainText(TypedDict):
    type: Literal["plain_text"]
    text: str
    emoji: NotRequired[bool]

@final
class SlackMessageBlockCompositionMrkdwn(TypedDict):
    type: Literal["mrkdwn"]
    text: str
    verbatim: NotRequired[bool]

SlackMessageBlockCompositionText = (
    SlackMessageBlockCompositionPlainText | SlackMessageBlockCompositionMrkdwn
)

@final
class SlackMessageBlockElementButton(TypedDict):
    type: Literal["button"]
    text: SlackMessageBlockCompositionPlainText
    action_id: str
    url: NotRequired[str]
    value: NotRequired[str]
    style: NotRequired[str]
    confirm: NotRequired[object]
    accessibility_label: NotRequired[str]

@final
class SlackMessageBlockElementImage(TypedDict):
    type: Literal["image"]
    image_url: str
    alt_text: str

SlackMessageBlockElementInteractive = SlackMessageBlockElementButton

SlackMessageBlockElement = (
    SlackMessageBlockElementInteractive | SlackMessageBlockElementImage
)

@final
class SlackMessageBlockActions(TypedDict):
    type: Literal["actions"]
    block_id: NotRequired[str]
    elements: List[SlackMessageBlockElementInteractive]

@final
class SlackMessageBlockContext(TypedDict):
    type: Literal["context"]
    block_id: NotRequired[str]
    elements: List[SlackMessageBlockCompositionText | SlackMessageBlockElementImage]

@final
class SlackMessageBlockDivider(TypedDict):
    type: Literal["divider"]
    block_id: NotRequired[str]

@final
class SlackMessageBlockImage(TypedDict):
    type: Literal["image"]
    block_id: NotRequired[str]
    image_url: str
    alt_text: str
    title: NotRequired[SlackMessageBlockCompositionPlainText]
    image_width: NotRequired[int]
    image_height: NotRequired[int]
    image_bytes: NotRequired[int]
    is_animated: NotRequired[bool]
    fallback: NotRequired[str]

@final
class SlackMessageBlockSection(TypedDict):
    type: Literal["section"]
    block_id: NotRequired[str]
    text: NotRequired[SlackMessageBlockCompositionText]
    fields: NotRequired[List[SlackMessageBlockCompositionText]]
    accessory: NotRequired[SlackMessageBlockElement]

SlackMessageBlock = (
    SlackMessageBlockRichText
    | SlackMessageBlockCall
    | SlackMessageBlockActions
    | SlackMessageBlockContext
    | SlackMessageBlockDivider
    | SlackMessageBlockImage
    | SlackMessageBlockSection
)

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

class SlackMessageMe(SlackMessageStandardCommon):
    subtype: Literal["me_message"]

@final
class SlackMessageMeFinal(SlackMessageMe):
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

class SlackMessageSubtypeHuddleThreadRoom(TypedDict):
    id: str
    name: str
    media_server: str
    created_by: str
    date_start: int
    date_end: int
    participants: List[str]
    participant_history: List[str]
    participants_camera_on: List[str]
    participants_camera_off: List[str]
    participants_screenshare_on: List[str]
    participants_screenshare_off: List[str]
    canvas_thread_ts: str
    thread_root_ts: str
    channels: List[str]
    is_dm_call: bool
    was_rejected: bool
    was_missed: bool
    was_accepted: bool
    has_ended: bool
    background_id: str
    canvas_background: str
    is_prewarmed: bool
    is_scheduled: bool
    attached_file_ids: List[str]
    media_backend_type: str
    display_id: str
    external_unique_id: str
    app_id: str
    call_family: str
    pending_invitees: Dict[str, str]

class SlackMessageSubtypeHuddleThread(SlackMessageStandardCommon):
    subtype: Literal["huddle_thread"]
    channel: str
    permalink: str
    no_notifications: bool
    room: SlackMessageSubtypeHuddleThreadRoom

@final
class SlackMessageSubtypeHuddleThreadFinal(SlackMessageSubtypeHuddleThread):
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
    | SlackMessageMeFinal
    | SlackMessageThreadParentNotSubscribedFinal
    | SlackMessageThreadParentSubscribedFinal
    | SlackMessageWithFilesFinal
    | SlackMessageSubtypeHuddleThreadFinal
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

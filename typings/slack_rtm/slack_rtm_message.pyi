from slack_api.slack_conversations_history import (
    SlackMessage,
    SlackMessageMe,
    SlackMessageStandardCommon,
    SlackMessageSubtypeBotAdd,
    SlackMessageSubtypeBotMessage,
    SlackMessageSubtypeBotRemove,
    SlackMessageSubtypeChannelJoin,
    SlackMessageSubtypeChannelLeave,
    SlackMessageSubtypeHuddleThread,
    SlackMessageSubtypeHuddleThreadRoom,
    SlackMessageThreadParentNotSubscribed,
    SlackMessageThreadParentSubscribed,
    SlackMessageWithFiles,
)
from typing_extensions import Literal, NotRequired, TypedDict, final

class SlackRtmHello(TypedDict):
    type: Literal["hello"]
    fast_reconnect: bool
    region: str
    start: bool
    host_id: str

@final
class SlackMessageStandardRtm(SlackMessageStandardCommon):
    channel: str

@final
class SlackMessageMeRtm(SlackMessageMe):
    channel: str

@final
class SlackMessageThreadParentNotSubscribedRtm(SlackMessageThreadParentNotSubscribed):
    channel: str

@final
class SlackMessageThreadParentSubscribedRtm(SlackMessageThreadParentSubscribed):
    channel: str

@final
class SlackMessageWithFilesRtm(SlackMessageWithFiles):
    channel: str

@final
class SlackMessageSubtypeHuddleThreadRtm(SlackMessageSubtypeHuddleThread):
    event_ts: str
    suppress_notification: bool

@final
class SlackMessageSubtypeBotMessageRtm(SlackMessageSubtypeBotMessage):
    channel: str

@final
class SlackMessageSubtypeBotRemoveRtm(SlackMessageSubtypeBotRemove):
    channel: str

@final
class SlackMessageSubtypeBotAddRtm(SlackMessageSubtypeBotAdd):
    channel: str

@final
class SlackMessageSubtypeChannelJoinRtm(SlackMessageSubtypeChannelJoin):
    channel: str

@final
class SlackMessageSubtypeChannelLeaveRtm(SlackMessageSubtypeChannelLeave):
    channel: str

@final
class SlackMessageChanged(TypedDict):
    type: Literal["message"]
    subtype: Literal["message_changed"]
    message: SlackMessage
    previous_message: SlackMessage
    channel: str
    hidden: bool
    ts: str
    event_ts: str

@final
class SlackMessageDeleted(TypedDict):
    type: Literal["message"]
    subtype: Literal["message_deleted"]
    previous_message: SlackMessage
    channel: str
    hidden: bool
    ts: str
    deleted_ts: str
    event_ts: str

@final
class SlackMessageReplied(TypedDict):
    type: Literal["message"]
    subtype: Literal["message_replied"]
    message: SlackMessage
    channel: str
    hidden: bool
    ts: str
    event_ts: str

@final
class SlackReactionItem(TypedDict):
    type: Literal["message", "file", "file_comment"]
    channel: str
    ts: str

@final
class SlackReactionAdded(TypedDict):
    type: Literal["reaction_added"]
    user: str
    reaction: str
    item: SlackReactionItem
    item_user: NotRequired[str]
    event_ts: str
    ts: str

@final
class SlackReactionRemoved(TypedDict):
    type: Literal["reaction_removed"]
    user: str
    reaction: str
    item: SlackReactionItem
    item_user: NotRequired[str]
    event_ts: str
    ts: str

class SlackShRoomHuddle(TypedDict):
    channel_id: str

@final
class SlackShRoomJoin(TypedDict):
    type: Literal["sh_room_join"]
    room: SlackMessageSubtypeHuddleThreadRoom
    user: str
    huddle: SlackShRoomHuddle
    event_ts: str
    ts: str

@final
class SlackShRoomUpdate(TypedDict):
    type: Literal["sh_room_update"]
    room: SlackMessageSubtypeHuddleThreadRoom
    user: str
    huddle: SlackShRoomHuddle
    event_ts: str
    ts: str

@final
class SlackUserTyping(TypedDict):
    type: Literal["user_typing"]
    channel: str
    thread_ts: NotRequired[str]
    id: int
    user: str

SlackMessageRtm = (
    SlackMessageStandardRtm
    | SlackMessageMeRtm
    | SlackMessageThreadParentNotSubscribedRtm
    | SlackMessageThreadParentSubscribedRtm
    | SlackMessageWithFilesRtm
    | SlackMessageSubtypeHuddleThreadRtm
    | SlackMessageSubtypeBotMessageRtm
    | SlackMessageSubtypeBotRemoveRtm
    | SlackMessageSubtypeBotAddRtm
    | SlackMessageSubtypeChannelJoinRtm
    | SlackMessageSubtypeChannelLeaveRtm
)

SlackRtmMessage = (
    SlackRtmHello
    | SlackMessageRtm
    | SlackMessageChanged
    | SlackMessageDeleted
    | SlackMessageReplied
    | SlackReactionAdded
    | SlackReactionRemoved
    | SlackShRoomJoin
    | SlackShRoomUpdate
    | SlackUserTyping
)

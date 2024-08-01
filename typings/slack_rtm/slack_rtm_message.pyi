from typing import List

from slack_api.slack_conversations_history import (
    SlackMessage,
    SlackMessageMe,
    SlackMessageStandardCommon,
    SlackMessageSubtypeBotAdd,
    SlackMessageSubtypeBotMessage,
    SlackMessageSubtypeBotRemove,
    SlackMessageSubtypeChannelJoin,
    SlackMessageSubtypeChannelLeave,
    SlackMessageSubtypeChannelTopic,
    SlackMessageSubtypeHuddleThread,
    SlackMessageSubtypeHuddleThreadRoom,
    SlackMessageThreadBroadcast,
    SlackMessageThreadParentCommon,
    SlackMessageThreadParentNotSubscribed,
    SlackMessageThreadParentSubscribed,
    SlackMessageWithFiles,
)
from slack_api.slack_conversations_info import SlackConversationsInfo
from slack_api.slack_conversations_replies import SlackMessageThreadCommon
from slack_api.slack_usergroups_info import SlackUsergroupInfoCommon
from slack_api.slack_users_info import SlackUserInfoPerson
from typing_extensions import Literal, NotRequired, TypedDict, final

class SlackRtmHello(TypedDict):
    type: Literal["hello"]
    fast_reconnect: bool
    region: str
    start: bool
    host_id: str

class SlackRtmErrorError(TypedDict):
    msg: str
    code: int
    source: str
    retry_after: NotRequired[int]  # Only with msg Ratelimited, code 17

class SlackRtmError(TypedDict):
    type: Literal["error"]
    error: SlackRtmErrorError

class SlackRtmReconnectUrl(TypedDict):
    type: Literal["reconnect_url"]
    url: str

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
class SlackMessageThreadRtm(SlackMessageThreadCommon):
    channel: str
    event_ts: str
    source_team: str
    suppress_notification: NotRequired[bool]
    user_team: str

@final
class SlackMessageThreadBroadcastRtm(SlackMessageThreadBroadcast):
    channel: str
    event_ts: str
    source_team: str
    suppress_notification: NotRequired[bool]
    user_team: str

@final
class SlackMessageWithFilesRtm(SlackMessageWithFiles):
    channel: str

@final
class SlackMessageSubtypeHuddleThreadRtm(SlackMessageSubtypeHuddleThread):
    event_ts: str
    suppress_notification: NotRequired[bool]

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
class SlackMessageSubtypeChannelTopicRtm(SlackMessageSubtypeChannelTopic):
    channel: str
    team: str
    event_ts: str

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
    message: SlackMessageThreadParentCommon
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

@final
class SlackImOpen(TypedDict):
    type: Literal["im_open"]
    user: str
    channel: str
    event_ts: str

@final
class SlackImClose(TypedDict):
    type: Literal["im_close"]
    user: str
    channel: str
    event_ts: str

@final
class SlackMpimOpen(TypedDict):
    type: Literal["mpim_open", "group_open"]
    is_mpim: Literal[True]
    user: str
    channel: str
    event_ts: str

@final
class SlackMpimClose(TypedDict):
    type: Literal["mpim_close", "group_close"]
    is_mpim: Literal[True]
    user: str
    channel: str
    event_ts: str

@final
class SlackChannelJoined(TypedDict):
    type: Literal["channel_joined", "group_joined"]
    channel: SlackConversationsInfo

@final
class SlackChannelLeft(TypedDict):
    type: Literal["channel_left", "group_left"]
    channel: str
    actor_id: str
    event_ts: str

class SlackNotImMarked(TypedDict):
    channel: str
    ts: str
    unread_count: int
    unread_count_display: int
    num_mentions: int
    num_mentions_display: int
    mention_count: int
    mention_count_display: int
    event_ts: str

@final
class SlackChannelMarked(SlackNotImMarked):
    type: Literal["channel_marked"]

@final
class SlackGroupMarked(SlackNotImMarked):
    type: Literal["group_marked"]
    is_mpim: Literal[False]

@final
class SlackMpImMarked(SlackNotImMarked):
    type: Literal["mpim_marked"]
    is_mpim: Literal[True]

@final
class SlackImMarked(TypedDict):
    type: Literal["im_marked"]
    channel: str
    ts: str
    dm_count: int
    unread_count_display: int
    num_mentions_display: int
    mention_count_display: int
    event_ts: str

class SlackThreadSubscription(TypedDict):
    type: Literal["thread"]
    channel: str
    thread_ts: str
    date_create: int
    active: bool
    last_read: str

# Dummy event to make sure we check that subscription is of type thead when used
class SlackThreadSubscriptionUnknown(TypedDict):
    type: Literal["unknown"]

@final
class SlackThreadMarked(TypedDict):
    type: Literal["thread_marked"]
    subscription: SlackThreadSubscription | SlackThreadSubscriptionUnknown
    event_ts: str

@final
class SlackThreadSubscribed(TypedDict):
    type: Literal["thread_subscribed"]
    subscription: SlackThreadSubscription | SlackThreadSubscriptionUnknown
    event_ts: str

@final
class SlackThreadUnsubscribed(TypedDict):
    type: Literal["thread_unsubscribed"]
    subscription: SlackThreadSubscription | SlackThreadSubscriptionUnknown
    event_ts: str

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

@final
class SlackPrefChange(TypedDict):
    type: Literal["pref_change"]
    name: str
    value: str

@final
class SlackUserStatusChanged(TypedDict):
    type: Literal["user_status_changed"]
    user: SlackUserInfoPerson
    cache_ts: str
    event_ts: str

class SlackUserInvalidatedUser(TypedDict):
    id: str

@final
class SlackUserInvalidated(TypedDict):
    type: Literal["user_invalidated"]
    user: SlackUserInvalidatedUser
    event_ts: str

class SlackSubteam(SlackUsergroupInfoCommon):
    users: List[str]

class SlackSubteamCreated(TypedDict):
    type: Literal["subteam_created"]
    subteam: SlackSubteam
    event_ts: str

class SlackSubteamUpdated(TypedDict):
    type: Literal["subteam_updated"]
    subteam: SlackSubteam
    event_ts: str

class SlackSubteamMembersChanged(TypedDict):
    type: Literal["subteam_members_changed"]
    subteam_id: str
    date_previous_update: int
    date_update: int
    added_users: List[str]
    added_users_count: int
    removed_users: List[str]
    removed_users_count: int
    team_id: str
    event_ts: str

class SlackSubteamSelfAdded(TypedDict):
    type: Literal["subteam_self_added"]
    subteam_id: str
    event_ts: str

class SlackSubteamSelfRemoved(TypedDict):
    type: Literal["subteam_self_removed"]
    subteam_id: str
    event_ts: str

SlackMessageRtm = (
    SlackMessageStandardRtm
    | SlackMessageMeRtm
    | SlackMessageThreadParentNotSubscribedRtm
    | SlackMessageThreadParentSubscribedRtm
    | SlackMessageThreadRtm
    | SlackMessageThreadBroadcastRtm
    | SlackMessageWithFilesRtm
    | SlackMessageSubtypeHuddleThreadRtm
    | SlackMessageSubtypeBotMessageRtm
    | SlackMessageSubtypeBotRemoveRtm
    | SlackMessageSubtypeBotAddRtm
    | SlackMessageSubtypeChannelJoinRtm
    | SlackMessageSubtypeChannelLeaveRtm
    | SlackMessageSubtypeChannelTopicRtm
)

SlackRtmMessage = (
    SlackRtmHello
    | SlackRtmError
    | SlackRtmReconnectUrl
    | SlackMessageRtm
    | SlackMessageChanged
    | SlackMessageDeleted
    | SlackMessageReplied
    | SlackReactionAdded
    | SlackReactionRemoved
    | SlackImOpen
    | SlackImClose
    | SlackMpimOpen
    | SlackMpimClose
    | SlackChannelJoined
    | SlackChannelLeft
    | SlackChannelMarked
    | SlackGroupMarked
    | SlackMpImMarked
    | SlackImMarked
    | SlackThreadMarked
    | SlackThreadSubscribed
    | SlackThreadUnsubscribed
    | SlackShRoomJoin
    | SlackShRoomUpdate
    | SlackUserTyping
    | SlackPrefChange
    | SlackUserStatusChanged
    | SlackUserInvalidated
    | SlackSubteamCreated
    | SlackSubteamUpdated
    | SlackSubteamMembersChanged
    | SlackSubteamSelfAdded
    | SlackSubteamSelfRemoved
)

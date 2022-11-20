from typing import TypedDict

class SlackTopic(TypedDict):
    value: str
    creator: str
    last_set: int

class SlackPurpose(TypedDict):
    value: str
    creator: str
    last_set: int

class SlackConversationCommon(TypedDict):
    id: str

class SlackConversationCommonNotIm(SlackConversationCommon):
    created: int
    creator: str
    is_archived: bool
    is_channel: bool
    is_ext_shared: bool
    is_general: bool
    is_group: bool
    is_im: bool
    is_member: bool
    is_mpim: bool
    is_org_shared: bool
    is_pending_ext_shared: bool
    is_private: bool
    is_shared: bool
    name_normalized: str
    name: str
    num_members: int
    parent_conversation: None
    pending_connected_team_ids: list
    pending_shared: list
    previous_names: list[str]
    purpose: SlackPurpose
    shared_team_ids: list[str]
    topic: SlackTopic
    unlinked: int

class SlackConversationPublic(SlackConversationCommonNotIm):
    num_members: int
    previous_names: list[str]

class SlackConversationPrivate(SlackConversationCommonNotIm):
    num_members: int

class SlackConversationMpim(SlackConversationCommonNotIm):
    num_members: int

class SlackConversationGroup(SlackConversationCommonNotIm):
    is_open: bool
    last_read: str
    priority: int

class SlackConversationIm(SlackConversationCommon):
    created: int
    is_archived: bool
    is_im: bool
    is_org_shared: bool
    is_user_deleted: bool
    priority: int
    user: str

SlackConversationNotIm = (
    SlackConversationPublic
    | SlackConversationPrivate
    | SlackConversationMpim
    | SlackConversationGroup
)
SlackConversationInfo = SlackConversationNotIm | SlackConversationIm

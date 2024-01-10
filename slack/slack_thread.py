from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING, Dict, Generator, Mapping, Optional, Set, Tuple

from slack.log import print_exception_once
from slack.slack_buffer import SlackBuffer
from slack.slack_message import SlackMessage, SlackTs
from slack.slack_user import SlackUser
from slack.task import gather

if TYPE_CHECKING:
    from typing_extensions import Literal

    from slack.slack_conversation import SlackConversation
    from slack.slack_workspace import SlackWorkspace


class SlackThread(SlackBuffer):
    def __init__(self, parent: SlackMessage) -> None:
        super().__init__()
        self.parent = parent
        self._reply_users: Set[SlackUser] = set()

    @property
    def workspace(self) -> SlackWorkspace:
        return self.parent.workspace

    @property
    def conversation(self) -> SlackConversation:
        return self.parent.conversation

    @property
    def context(self) -> Literal["conversation", "thread"]:
        return "thread"

    @property
    def members(self) -> Generator[SlackUser, None, None]:
        for user in self._reply_users:
            yield user

    @property
    def messages(self) -> Mapping[SlackTs, SlackMessage]:
        return self.parent.replies

    @property
    def last_read(self) -> Optional[SlackTs]:
        return self.parent.last_read

    def get_name_and_buffer_props(self) -> Tuple[str, Dict[str, str]]:
        conversation_name = self.parent.conversation.name_with_prefix("full_name")
        name = f"{conversation_name}.${self.parent.hash}"
        short_name = f" ${self.parent.hash}"

        return name, {
            "short_name": short_name,
            "title": "topic",
            "input_multiline": "1",
            "localvar_set_type": self.parent.conversation.buffer_type,
            "localvar_set_slack_type": "thread",
            "localvar_set_nick": self.workspace.my_user.nick.raw_nick,
            "localvar_set_channel": name,
            "localvar_set_server": self.workspace.name,
            "localvar_set_completion_default_template": "${weechat.completion.default_template}|%(slack_channels)|%(slack_emojis)",
        }

    async def buffer_switched_to(self):
        await super().buffer_switched_to()
        await self.fill_history()

    async def set_hotlist(self):
        self.history_needs_refresh = True
        await self.fill_history()

    async def print_history(self):
        messages = chain([self.parent], self.parent.replies.values())
        self.history_pending_messages.clear()
        for message in list(messages):
            if self.last_printed_ts is None or message.ts > self.last_printed_ts:
                await self.print_message(message)

        while self.history_pending_messages:
            message = self.history_pending_messages.pop(0)
            await self.print_message(message)

    async def fill_history(self):
        if self.history_pending:
            return

        with self.loading():
            self.history_pending = True

            if self.parent.reply_history_filled and not self.history_needs_refresh:
                await self.print_history()
                self.history_pending = False
                return

            messages = await self.parent.conversation.fetch_replies(self.parent.ts)

            if self.history_needs_refresh:
                await self.rerender_history()

            sender_user_ids = [m.sender_user_id for m in messages if m.sender_user_id]
            self.workspace.users.initialize_items(sender_user_ids)

            sender_bot_ids = [
                m.sender_bot_id
                for m in messages
                if m.sender_bot_id and not m.sender_user_id
            ]
            self.workspace.bots.initialize_items(sender_bot_ids)

            await gather(*(message.render(self.context) for message in messages))
            await self.print_history()

            self.history_needs_refresh = False
            self.history_pending = False

    async def print_message(self, message: SlackMessage):
        await super().print_message(message)
        sender_user_id = message.sender_user_id
        if sender_user_id is not None:
            try:
                sender_user = await self.workspace.users[sender_user_id]
                self._reply_users.add(sender_user)
            except Exception as e:
                print_exception_once(e)

    async def mark_read(self):
        # subscriptions.thread.mark is only available for session tokens
        if self.workspace.token_type != "session":
            return

        # last_read can only be set if it exists (which is on threads you're subscribed to)
        if self.last_read is None:
            return

        last_read_line_ts = self.last_read_line_ts()
        if last_read_line_ts and last_read_line_ts != self.last_read:
            await self._api.subscriptions_thread_mark(
                self.parent.conversation, self.parent.ts, last_read_line_ts
            )

    async def post_message(
        self,
        text: str,
        thread_ts: Optional[SlackTs] = None,
        broadcast: bool = False,
    ):
        await super().post_message(text, thread_ts or self.parent.ts, broadcast)

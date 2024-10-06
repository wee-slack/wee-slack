from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING, Dict, Generator, Mapping, Optional, Set, Tuple

from slack.slack_message import MessageContext, SlackMessage, SlackTs
from slack.slack_message_buffer import SlackMessageBuffer
from slack.slack_user import Nick
from slack.task import gather

if TYPE_CHECKING:
    from typing_extensions import Literal

    from slack.slack_conversation import SlackConversation
    from slack.slack_workspace import SlackWorkspace


class SlackThread(SlackMessageBuffer):
    def __init__(self, parent: SlackMessage) -> None:
        super().__init__()
        self.parent = parent
        self._reply_nicks: Set[Nick] = set()

    @property
    def workspace(self) -> SlackWorkspace:
        return self.parent.workspace

    @property
    def conversation(self) -> SlackConversation:
        return self.parent.conversation

    @property
    def context(self) -> MessageContext:
        return "thread"

    @property
    def members(self) -> Generator[Nick, None, None]:
        for nick in self._reply_nicks:
            if nick.type == "user":
                yield nick

    @property
    def messages(self) -> Mapping[SlackTs, SlackMessage]:
        return self.parent.replies

    @property
    def last_read(self) -> SlackTs:
        return self.parent.last_read

    def get_name_and_buffer_props(self) -> Tuple[str, Dict[str, str]]:
        conversation_name = self.parent.conversation.name_with_prefix("full_name")
        name = f"{conversation_name}.${self.parent.hash}"
        short_name = f" ${self.parent.hash}"

        return name, {
            "short_name": short_name,
            "title": "topic",
            "input_prompt": self.workspace.my_user.nick.raw_nick,
            "input_multiline": "1",
            "localvar_set_type": self.parent.conversation.buffer_type,
            "localvar_set_slack_type": "thread",
            "localvar_set_nick": self.workspace.my_user.nick.raw_nick,
            "localvar_set_channel": name,
            "localvar_set_server": self.workspace.name,
            "localvar_set_workspace": self.workspace.name,
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
        if self.is_loading:
            return

        with self.loading():
            if self.parent.reply_history_filled and not self.history_needs_refresh:
                await self.print_history()
                return

            _, messages = await self.parent.conversation.fetch_replies(self.parent.ts)

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

    async def print_message(self, message: SlackMessage):
        did_print = await super().print_message(message)

        if did_print:
            nick = await message.nick()
            self._reply_nicks.add(nick)

        return did_print

    async def mark_read(self):
        # subscriptions.thread.mark is only available for session tokens
        if self.workspace.token_type != "session":
            return

        # last_read can only be set on subscribed threads
        if not self.parent.subscribed:
            return

        last_read_line_ts = self.last_read_line_ts()
        if last_read_line_ts and last_read_line_ts != self.last_read:
            await self.api.subscriptions_thread_mark(
                self.parent.conversation, self.parent.ts, last_read_line_ts
            )

    async def post_message(
        self,
        text: str,
        thread_ts: Optional[SlackTs] = None,
        # The API doesn't support broadcast for /me messages, so ensure only
        # either broadcast or me_message is set
        message_type: Literal["standard", "broadcast", "me_message"] = "standard",
    ):
        await super().post_message(
            text=text,
            thread_ts=thread_ts or self.parent.ts,
            message_type=message_type,
        )

# Changelog

## Next version

## 2.2.0 (2018-11-12)

- Print user friendly error when trying to send a message in the team buffer (fixes #543).
- Show inviter for join events (fixes #538).
- Don't print whitespace before join/leave messages.
- Colorize edits and reactions, using options `color_reaction_suffix` and `color_edited_suffix` (PR #608, PR #623, PR #660).
- Use highlight notifications for MPDMs.
- Notify of new mentions in threads and new messages in threads you participate in (fixes #572, fixes #535, PR #617).
- Set correct tags for topic messages.
- Support hiding activity from muted channels (fixes #456, PR #457). Adds a `muted_channels_activity` option to control if you see activity in muted channels.
- Use an adaptive eventrouter timer (fixes #523, PR #631). Reduces CPU usage.
- Add option `thread_messages_in_channel` to show thread messages in parent channel (fixes #546, PR #616).
- Allow reactions and edit of messages in threads (fixes #416, fixes #442, fixes #534, PR #622).
- Rename option `thread_suffix_color` to `color_thread_suffix` so color options are grouped together. The value that is set will be migrated.
- Gray out muted channels in buflist, using option `color_buflist_muted_channels` (PR #644).
- Fix loading history with deleted attachment (fixes #640, PR #641).
- Add support for cursor mode and mouse mode (fixes #429, fixes #553, fixes #541, PR #626, PR #652, PR #650).
- Fix typing and completion errors in team buffer (fixes #380, PR #638).
- Match nicks with parenthesis, apostrophe and/or unicode (fixes #545, fixes #570, fixes #618, PR #649, PR #657).
- Fix /whois when user has a status text set (fixes #624, PR #651).
- Fix bug preventing first line in buffer from being changed (PR #655).
- Fix /reply and /thread in relay clients (fixes #547, fixes #615).
- Support using /thread for already opened threads (fixes #533).

## 2.1.1 and earlier

Unfortunately, no changelog has been written for these versions.

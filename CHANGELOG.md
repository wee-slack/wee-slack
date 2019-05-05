# Changelog

## 2.3.0 (2019-05-05)

- Python 3 support. Python 2 will continue to be supported at least until the end of 2019 (fixes #258, fixes #331, fixes #555, fixes #576, fixes #598).
- Improve detection of connection loss to the server, and improve reconnection (fixes #238, fixes #480, fixes #561, fixes #687).
- Add option `files_download_location` to download uploaded files automatically (fixes #562, PR #666).
- Add option `show_buflist_presence` to show/hide presence from buflist (PR #558).
- Add command `/help` and add descriptions for all commands (fixes #363).
- Remove command `/leave` (weechat aliases it to `/part` by default so we don't need to implement it specifically).
- Remove command `/slack p` (only used for debugging).
- Remove command `/slack openweb`, use `/slack linkarchive` instead.
- Make command `/thread` open last thread in channel when called without arguments (PR #677).
- Support command `/away -all` for marking you away on all servers/teams (fixes #596).
- Show human readable names for user groups properly (PR #680).
- Add tab completion of user groups (PR #680).
- Support uploading files to threads (fixes #672, PR #683).
- Include threads when marking latest message as read (PR #653).
- Some fixes for formatting of messages (bold/italic) (PR #567).
- Show human readable references (e.g. user names) instead of ids in topic (PR #665).
- Show join/leave correctly in private channels (fixes #625, PR #684).
- Print error if user/channel is not found when querying/joining (fixes #597).
- Print a message when another client or the server closes an IM.
- Various small bug fixes.

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

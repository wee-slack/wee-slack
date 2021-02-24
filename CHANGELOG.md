# Changelog

## 2.7.0 (2021-02-24)

Note that this version changes the default value of the `background_load_all_history` option to `true`, but this will not change for existing installations. It is recommended to set it to `true` unless you experience performance issues. If you keep it at `false` you will experience these issues:

- Channels will not be shown as unread when wee-slack loads, even if there are unread messages. Messages which arrive after wee-slack has loaded however will mark the channel as unread.
- If messages arrive while the connection to Slack is lost (e.g. during suspend), they will not appear in the hotlist.

The reason for these issues now being present with `background_load_all_history` set to `false` is that the API has changed, so we can't check for unread messages without loading the history anymore.

### Slack API changes

- Change to the new Conversations API. The old API will stop working on 2021-02-24, which means that older versions of wee-slack will not work after this (fixes #792).

### Features

- Rewrite how the channel history is fetched. This fixes some issues with fetching history after loosing connection and reconnecting (fixes #629, fixes #715, closes #732, PR #774).
- Change `/rehistory` command to only print the buffer again, not fetch the history from Slack again, unless the `-remote` option is provided.
- Better support for renaming buffers (fixes #563).
- Use the `weechat.history.max_buffer_lines_number` option to decide how much backlog to keep.
- Add an option `history_fetch_count` for how much history to fetch (fixes #376).
- Rename buffers from `<team>.slack.com` to `slack.<team>` (fixes #709).
- Include a prefix character in front of attachments.
- Support colorizing attachment prefix or line (fixes #424, fixes #426).
- Support creating channels with the new command `/slack create` (fixes #415).
- Support custom indent in buflist for threads (see [the last comment](https://github.com/wee-slack/wee-slack/issues/783#issuecomment-658435310) in #783 for details).
- Support global placement of the `weemoji.json` file.
- Add support to disable teammate link previews (PR #815).

### Bug fixes

- More robust handling of file modes (PR #771).
- Prevent rendering two versions of the message text in certain cases.
- Increase duration of typing notices, so they remain continously for a person that is continously typing, instead of disappearing and reappering every four seconds.
- Fix typing indicators in buflist for DMs and MPDMs.
- Only fetch members for joined channels when getting history, prevents unnecessary requests and rate limiting (fixes #775).
- Fix issues with the `thread_messages_in_channel` option in certain channels (fixes #664).
- Support notifying thread messages for old threads (parent message is out of the backlog) and before channel history is loaded (fixes #619, fixes #754).
- Mark thread as read when closing buffer.
- Store message ts in line tags instead of misusing `date_printed` (fixes #514).
- Disable print hooks when printing old/debug messages (fixes #629, fixes #756).
- When changing latest message in a channel, print new lines if needed (previously, the lines would be joined if the new version of the message had more lines than the old, and this is still the case for older messages).
- Remove buffer notify option for unmuted buffers (fixes #746).
- Fix buffers not changing color in buflist when (un)muted.
- Fix thread bot messages appearing in channel instead of thread (fixes #749).
- Set correct localvar type for threads in pms (fixes #789).
- Use `slack_timeout` for websocket connection (relates to #793).
- Don't display the typing indicator for muted conversations (PR #794).
- Print error message when sending message fails (relates to #797).
- Don't escape <>& in me messages (fixes #704, closes #822).

## 2.6.0 (2020-05-06)

### Features

- Support subscribing to threads, showing which threads are subscribed to and marking threads as read (PR #758). Note that subscribing and marking threads as read only work when you use a session token. Read more about it [in the readme](https://github.com/wee-slack/wee-slack#4-add-your-slack-api-tokens).
- Don't notify about threads when they're opened in the channel (PR #763). This can be controlled with the new option `notify_subscribed_threads`.
- Support commands consisting of multiple lines (fixes #728).
- Support toggling a reaction by right clicking on an emoji or emoji name.
- Don't connect to the teams if auto connect is disabled (fixes #613).
- Show footer and files in attachments.
- Print error message when editing a message fails.
- Don't print link fallback if it's equal to the link.
- Improve deduplication of links in attachments.
- Place `record_events` files in separate directories for each team.

### Bug fixes

- Prevent errors after running `/upgrade` (fixes #275, fixes #309, fixes #310).
- Fix `record_events` not working (fixes #761). This bug was introduced in version 2.5.0.
- Fix bug which made `/slack` complete thread hashes. This bug was introduced in version 2.5.0.
- Fix `/slack status` not completing emojis when trying to complete without typing anything first.
- Fix error on some deleted message events (notably Giphy previews).

### Slack API changes

- Fix `/slack register` not working after Slack made their OAuth implementation stricter.
- Use the `reply_count` property of a message instead of `replies`, because `replies` isn't provided anymore.

## 2.5.0 (2020-03-25)

Note that you need to update the `weemoji.json` file when upgrading to this version.

### Features

- Add a proper page for OAuth which shows the code so you don't have to pull it out of the url.
- Render emojis as emoji characters (fixes #465). Also allow them to be rendered both as emoji characters and as the name (PR #752).
- Support sending reactions with emoji characters (fixes #236, fixes #575).
- Add ability to broadcast a thread message to the rest of the channel (PR #753). Use `/reply -alsochannel` to do this.
- Add support for Slack Blocks (fixes #726, PR #729).
- Show away in away bar item when presence is away.
- Set presence to active when switching buffer or calling `/slack back`.
- Add options for hard coded colors (fixes #681).
- Show reactions you have added in a different color (fixes #713).
- Support using a different color for each thread suffix/prefix (fixes #716).
- (Un)merge team buffers when `irc.look.server_buffer` is changed (fixes #712).
- Show the parent message as the first message in a thread (fixes #705).
- Support adding a token you already have with `/slack register <token>`.
- Print error message when reaction couldn't be added/removed.
- Print error if trying to use `/thread` in team buffer (fixes #737).

### Bug fixes

- Preserve thread channels across reconnections and `/rehistory` (fixes #714).
- Set `highlight_words` for new channels and thread channels (fixes #736).
- Reply to parent message if trying to reply to thread message (fixes #751).
- Fix bug where not all members in shared channels or channels converted from public to private were shown.
- Don't switch to the debug buffer when config is changed and `debug_mode` is on.
- Print warning when having two tokens for the same team, instead of failing with 100 % cpu usage (fixes #734).
- Fix bug when handling nicks with non-ascii characters on Python 2 (fixes #747). This bug was introduced in 2.4.0.
- Readd tag `logger_backlog` for backlog messages. This was inadvertently removed in 2.4.0.

## 2.4.0 (2020-01-16)

- Support regex flags i, m and s for message edits.
- Allow %h (weechat home) replacement in download_location (PR #690).
- Render "by invitation from" before reactions.
- The command `/slack status` now prints the status if no arguments are given. Pass `-delete` to unset the status (fixes #574).
- Add completion for channel names (fixes #235).
- Add completion for all command arguments.
- Allow completion of emoji with a prefix (fixes #580).
- For `/slack upload` remove escape characters from path if file is not found (fixes #360).
- For `/slack upload` resolve relative paths.
- Expose more information in /whois (PR #700).
- Add option `use_full_names` to only use full names (fixes #100).
- Support nicks prefixed with @ in the `/msg` command.
- Show member status in the `/slack channels` command.
- Show handle when listing usergroup members.
- Add support for the /invite command (fixes #698).
- Add the usergroups you are a member of to highlight words (fixes #272, fixes #367, fixes #542).
- Add a command to list the Slack teams.
- Some changes on line tags, most notably irc_smart_filter is replaced with irc_join and irc_part because no smartness is implemented. Search for "tag" in the commit messages to see the other changes.
- Prevent highlight in debug buffer.
- Don't log backlog messages to the logfile (fixes #663).
- Use proper nicks for mpdm names (fixes #498).
- Fallback to full name instead of username if display name is not set.
- Don't add deleted users to tab completion (fixes #703).
- Print responses and errors from /slack slash command (fixes #369, fixes #374).
- Fix option `record_events` (it was broken in 2.3.0).
- Fix output of the `/topic` command (PR #691).
- Set own nick to display name if set (fixes #692).
- Prevent crash when having mpdm with an external user.
- Prevent crash when script is reloaded if numpy is installed.
- Support topic changes for private channels (fixes #697).
- Fix attachment fields without titles (PR #707).
- Don't turn `#name` into a link to the private message (fixes #587).
- Render group notifications with @ instead of !.
- Support using display names in the `/slack slash` command.
- Print thread broadcast messages in parent channel (fixes #620).
- Add basic support for private channels converted from public (fixes most of #664).
- Better error messages.
- Various small bug fixes, see the commit messages for details.

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

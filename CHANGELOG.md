# Changelog

## 2.10.2 (2024-02-18)

Note: This will most likely be the last version before version 3.0.0, which is a mostly complete rewrite of the script with some breaking changes. Notably the configuration options have completely changed to be more in line with how the IRC plugin does it with a separate section for each Slack workspace. There will be some new features, but some existing features might also be dropped. Several bugs have been fixed, but of course new ones may have been introduced too.

### Bug fixes

- Fix rendering of text styles for certain messages (regression from version v2.10.0).
- Only open subscribed threads with `auto_open_threads` enabled (fixes #803, fixes #830).
- Mark conversation/thread as read when `/buffer set unread` is run.
- Handle millisecond-level timestamps in attachments (PR #905).
- Handle Firefox containers in `extract_token_from_browser.py` (PR #909).
- Properly fix rendering of `<` and `>` (fixes #908). The fix in v2.10.1 only fixed it for normal text, not e.g. code blocks and attachments.
- Support color rich text elements (fixes #912).
- Correctly show reactions with more than 50 users.
- Make /thread work on thread replies.
- Add no-secretstorage option for `extract_token_from_browser.py`.

## 2.10.1 (2023-09-22)

### Slack API changes

- Fix the connection to the websocket when using session (`xoxc-`) tokens. These connections started failing after a change in the Slack API which made wee-slack unable to run at all (fixes #901).

### Bug fixes

- Fix being invited to a private channel not working.
- Add join messages for your own user to hotlist (if unread).
- Prevent errors being printed in core buffer on events for unknown channels.
- Fix rendering of `<` and `>`. A regression in 2.10.0 made these be removed.
- Fix rendering of huddles. A regression in 2.10.0 made the text for huddle messages duplicated.
- Fix rendering of emojis when `render_emoji_as_string` is set to `both`. A regression in 2.10.0 made emojis show twice with this option (PR #902).
- Print an error message when running the `/reply` command without any arguments (fixes #900).

## 2.10.0 (2023-08-24)

### WeeChat compatibility

- Support multiline rendering in WeeChat >= 4.0.0.

### Features

- Display link to join huddle when started (PR #885).
- Support Chromium, Chrome and Firefox snap in `extract_token_from_browser.py` (PR #884).
- Detect default Firefox profile in `extract_token_from_browser.py` (PR #887).
- Support specifying profile to use in `extract_token_from_browser.py` (PR #884, PR #887).
- Read new local storage format for Firefox in `extract_token_from_browser.py` (PR #887).
- Automatically enable emoji/usergroups completion.
- Add info to get contents of a message (fixes #889).
- Filter channel list based on regular expression (PR #896).

### Bug fixes

- Support `/msg *` in thread buffers (fixes #888).
- Improve rendering of messages by using the `rich_text` block (fixes #354, fixes #550, fixes #893).

### Slack API changes

- Fix showing origin channel in previews of Slack messages when a message is linked after it was broken by an API change.

### Other changes

- Include a space between nicks in reaction string.
- Update Dockerfile to use XDG directories (PR #894).

## 2.9.1 (2022-10-30)

### WeeChat compatibility

- Update WeeChat version check to require >= 2.2. The reason for requiring this is that a feature of WeeChat 2.2 (specifying HTTP cookies) is necessary for adding support for the new type of session tokens added in version 2.9.0, so this should have been updated in that version.
- Update usage of some deprecated WeeChat API methods.

### Bug fixes

- Open open IMs and MPIMs on start, not just unread (fixes #875).
- Fix old type MPIMs not being marked as unread on start.
- Evaluate value of the `weechat.look.buffer_time_format` option (fixes #871).
- Fix link previews from apps not being recognized (fixes #834).
- Show useful link for Slack posts.
- Support receiving multiple header blocks in http responses. This was a regression introduced by implementing support for rate limiting in version 2.9.0.
- Fall back to bot id as nick instead of a blank nick if no other info is available (it should be possible to fetch the nick, but that's a remaining bug).

## 2.9.0 (2022-09-19)

Note that Slack will make a breaking change in their API on September 20, 2022 (the day after this release), which means that all earlier versions of wee-slack will stop working. This release adds support for the change and will not be affected by it.

Note that this will most likely be the last release supporting Python 2 (possibly apart from bug fixes and small features). The next major release will most likely require Python >= 3.3 or Python >= 3.6.

### Slack API changes

- Replaces usage of the `rtm.start` API method with other API methods. `rtm.start` will stop working on September 20, 2022 (fixes #866, PR #857).
- Add support for the new type of session tokens (tokens starting with `xoxc-`), i.e. tokens pulled out of the official client which doesn't require registering the wee-slack app in Slack (fixes #844, PR #857).
- Fix message changes not always being processed after API change.

### Bug fixes

- Fix alignment of multi line messages when `weechat.look.prefix_align` is set to `none`.
- Fix compatibility with Python 2, which was broken in version 2.8.0.
- Don't unhide buffers when reprinting messages (PR #839).
- Make sure IMs and group IMs with unread messages are shown at start (fixes #551, PR #859, PR #857).
- Properly retry requests when rate limited (PR #857).
- Fix `/query` command not working for new group IMs (fixes #852, PR #857).
- Include URL in message when block contains a URL (fixes #810, fixes #811, PR #863).

## 2.8.0 (2021-05-11)

### WeeChat compatibility

- Add compatibility with WeeChat >= 3.2 (XDG directories).

### Features

- Include channel name in file names for downloaded files (fixes #836).
- Add indicator for broadcast thread messages (PR #838).

### Bug fixes

- Fix nick not being shown for unknown/external users.
- Fix a bug where the first line would use `prefix_same_nick` after reprinting messages if the first and last message were from the same person.
- Fix some nicks missing in the nicklist of some channels (fixes #829).
- Fix new MPIMs (group private chats) not appearing (fixes #825, fixes #833).
- Fix some MPIMs showing up as private channels.

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
- Allow %h (WeeChat home) replacement in download_location (PR #690).
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
- Remove command `/leave` (WeeChat aliases it to `/part` by default so we don't need to implement it specifically).
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

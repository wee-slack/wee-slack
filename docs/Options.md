# Options

You can set these options by using:

```
/set plugins.var.python.slack.option_name value
```

You can also see all the options and set them them interactively by running `/fset slack`.

Note that the default value will be shown as an empty string in weechat.
The actual default values are listed below.

Most options require that you reload the script with `/python reload
slack` after changing it to take effect.

## Available options:

### auto_open_threads

**Default:** `false`

**Description:** Automatically open threads when mentioned or inresponse to own messages.

### background_load_all_history

**Default:** `true`

**Description:** Load the history for all channels in the background when the script is loaded, rather than waiting until the buffer is switched to. You can set this to false if you experience performance issues, however that causes some loss of functionality, see known issues in the readme.

### channel_name_typing_indicator

**Default:** `true`

**Description:** Change the prefix of a channel from # to > when someone is typing in it. Note that this will (temporarily) affect the sort order if you sort buffers by name rather than by number.

### color_buflist_muted_channels

**Default:** `darkgray`

**Description:** Color to use for muted channels in the buflist

### color_deleted

**Default:** `red`

**Description:** Color to use for deleted messages and files.

### color_edited_suffix

**Default:** `095`

**Description:** Color to use for (edited) suffix on messages that have been edited.

### color_reaction_suffix

**Default:** `darkgray`

**Description:** Color to use for the [:wave:(@user)] suffix on messages that have reactions attached to them.

### color_reaction_suffix_added_by_you

**Default:** `blue`

**Description:** Color to use for reactions that you have added.

### color_thread_suffix

**Default:** `lightcyan`

**Description:** Color to use for the [thread: XXX] suffix on messages that have threads attached to them. The special value "multiple" can be used to use a different color for each thread.

### color_typing_notice

**Default:** `yellow`

**Description:** Color to use for the typing notice.

### colorize_attachments

**Default:** `prefix`

**Description:** Whether to colorize attachment lines. Values: "prefix": Only colorize the prefix, "all": Colorize the whole line, "none": Don't colorize.

### colorize_private_chats

**Default:** `false`

**Description:** Whether to use nick-colors in DM windows.

### debug_level

**Default:** `3`

**Description:** Show only this level of debug info (or higher) when debug_mode is on. Lower levels -> more messages.

### debug_mode

**Default:** `false`

**Description:** Open a dedicated buffer for debug messages and start logging to it. How verbose the logging is depends on log_level.

### distracting_channels

**Default:** ``

**Description:** List of channels to hide.

### external_user_suffix

**Default:** `*`

**Description:** The suffix appended to nicks to indicate external users.

### files_download_location

**Default:** ``

**Description:** If set, file attachments will be automatically downloaded to this location. "%h" will be replaced by WeeChat home, "~/.weechat" by default. Requires WeeChat 2.2 or newer.

### group_name_prefix

**Default:** `&`

**Description:** The prefix of buffer names for groups (private channels).

### history_fetch_count

**Default:** `200`

**Description:** The number of messages to fetch for each channel when fetching history, between 1 and 1000.

### link_previews

**Default:** `true`

**Description:** Show previews of website content linked by teammates.

### map_underline_to

**Default:** `_`

**Description:** When sending underlined text to slack, use this formatting character for it. The default ("_") sends it as italics. Use "*" to send bold instead.

### muted_channels_activity

**Default:** `personal_highlights`

**Description:** Control which activity you see from muted channels, either none, personal_highlights, all_highlights or all. none: Don't show any activity. personal_highlights: Only show personal highlights, i.e. not @channel and @here. all_highlights: Show all highlights, but not other messages. all: Show all activity, like other channels.

### never_away

**Default:** `false`

**Description:** Poke Slack every five minutes so that it never marks you "away".

### notify_subscribed_threads

**Default:** `auto`

**Description:** Control if you want to see a notification in the team buffer when a thread you're subscribed to receives a new message, either auto, true or false. auto means that you only get a notification if auto_open_threads and thread_messages_in_channel both are false. Defaults to auto.

### notify_usergroup_handle_updated

**Default:** `false`

**Description:** Control if you want to see a notification in the team buffer when ausergroup's handle has changed, either true or false.

### record_events

**Default:** `false`

**Description:** Log all traffic from Slack to disk as JSON.

### render_bold_as

**Default:** `bold`

**Description:** When receiving bold text from Slack, render it as this in weechat.

### render_emoji_as_string

**Default:** `false`

**Description:** Render emojis as :emoji_name: instead of emoji characters. Enable this if your terminal doesn't support emojis, or set to 'both' if you want to see both renderings. Note that even though this is disabled by default, you need to place https://github.com/wee-slack/wee-slack/blob/master/weemoji.json in your weechat directory to enable rendering emojis as emoji characters.

### render_italic_as

**Default:** `italic`

**Description:** When receiving bold text from Slack, render it as this in weechat. If your terminal lacks italic support, consider using "underline" instead.

### send_typing_notice

**Default:** `true`

**Description:** Alert Slack users when you are typing a message in the input bar (Requires reload)

### server_aliases

**Default:** ``

**Description:** A comma separated list of `subdomain:alias` pairs. The alias will be used instead of the actual name of the slack (in buffer names, logging, etc). E.g `work:no_fun_allowed` would make your work slack show up as `no_fun_allowed` rather than `work.slack.com`.

### shared_name_prefix

**Default:** `%`

**Description:** The prefix of buffer names for shared channels.

### short_buffer_names

**Default:** `false`

**Description:** Use `foo.#channel` rather than `foo.slack.com.#channel` as the internal name for Slack buffers.

### show_buflist_presence

**Default:** `true`

**Description:** Display a `+` character in the buffer list for present users.

### show_reaction_nicks

**Default:** `false`

**Description:** Display the name of the reacting user(s) alongside each reactji.

### slack_api_token

**Default:** `INSERT VALID KEY HERE!`

**Description:** List of Slack API tokens, one per Slack instance you want to connect to. See the README for details on how to get these.

### slack_timeout

**Default:** `20000`

**Description:** How long (ms) to wait when communicating with Slack.

### switch_buffer_on_join

**Default:** `true`

**Description:** When /joining a channel, automatically switch to it as well.

### thread_messages_in_channel

**Default:** `false`

**Description:** When enabled shows thread messages in the parent channel.

### unfurl_auto_link_display

**Default:** `both`

**Description:** When displaying ("unfurling") links to channels/users/etc, determine what is displayed when the text matches the url without the protocol. This happens when Slack automatically creates links, e.g. from words separated by dots or email addresses. Set it to "text" to only display the text written by the user, "url" to only display the url or "both" (the default) to display both.

### unfurl_ignore_alt_text

**Default:** `false`

**Description:** When displaying ("unfurling") links to channels/users/etc, ignore the "alt text" present in the message and instead use the canonical name of the thing being linked to.

### unhide_buffers_with_activity

**Default:** `false`

**Description:** When activity occurs on a buffer, unhide it even if it was previously hidden (whether by the user or by the distracting_channels setting).

### use_full_names

**Default:** `false`

**Description:** Use full names as the nicks for all users. When this is false (the default), display names will be used if set, with a fallback to the full name if display name is not set.


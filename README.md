wee-slack
=========

A WeeChat native client for Slack.com. Provides supplemental features only available in the web/mobile clients such as: synchronizing read markers, typing notification, threads (and more)! Connects via the Slack API, and maintains a persistent websocket for notification of events.

![animated screenshot](https://github.com/wee-slack/wee-slack/raw/master/docs/slack.gif)

Table of Contents
-----------------
  * [Features](#features)
  * [Contributing](#contributing)
  * [Dependencies](#dependencies)
  * [Setup](#setup)
     * [1. Install dependencies](#1-install-dependencies)
     * [2. Install and load wee-slack](#2-install-and-load-wee-slack)
        * [From the WeeChat script repo](#from-the-weechat-script-repo)
        * [From the GitHub repo](#from-the-github-repo)
     * [3. Add your Slack API token(s)](#3-add-your-slack-api-tokens)
        * [Get a token with OAuth](#get-a-token-with-oauth)
        * [Get a session token](#get-a-session-token)
        * [Optional: Connecting to multiple teams](#optional-connecting-to-multiple-teams)
        * [Optional: Secure the tokens](#optional-secure-the-tokens)
  * [Commands and options](#commands-and-options)
     * [Threads](#threads)
     * [Emoji characters and tab completions of emoji names](#emoji-characters-and-tab-completions-of-emoji-names)
     * [Cursor and mouse mode](#cursor-and-mouse-mode)
  * [Removing a team](#removing-a-team)
  * [Optional settings](#optional-settings)
  * [FAQ](#faq)
     * [How do I keep the buffers sorted alphabetically or with a custom order?](#how-do-i-keep-the-buffers-sorted-alphabetically-or-with-a-custom-order)
     * [How do I group the buffers by team in the buffer list?](#how-do-i-group-the-buffers-by-team-in-the-buffer-list)
     * [How can I get system wide notifications for messages?](#how-can-i-get-system-wide-notifications-for-messages)
        * [Local notifications on Linux](#local-notifications-on-linux)
        * [Local notifications on macOS](#local-notifications-on-macos)
        * [Remote notifications](#remote-notifications)
     * [How do I send messages with multiple lines?](#how-do-i-send-messages-with-multiple-lines)
        * [For WeeChat &lt; 4.0.0](#for-weechat--400)
  * [Known issues](#known-issues)
  * [Debugging](#debugging)
  * [Support](#support)

Features
--------
  * [Threads](#threads) support
  * Slack status support
  * Slash commands (including custom ones)
  * Upload to slack capabilities
  * Emoji reactions
  * Edited messages work just like the official clients, where the original message changes and has (edited) appended.
  * Unfurled urls dont generate a new message, but replace the original with more info as it is received.
  * Regex message editing (s/oldtext/newtext/)
  * Smarter redraw of dynamic buffer info (much lower CPU %)
  * Multiple Teams supported. Just add multiple api tokens separated by commas
  * Replays history automatically during startup. (and sets read marker to the correct position in history)
  * Open channels synchronized with Slack. When you open/close a channel on another client it is reflected in wee-slack
  * Colorized nicks in chat
  * Supports bidirectional slack read notifications for all channels. (never reread the same messages on the web client or other devices).
  * Typing notification, so you can see when others are typing, and they can see when you type. Appears globally for direct messages
  * Away/back status handling
  * Expands/shows metadata for things like tweets/links
  * *Super fun* debug mode. See what the websocket is saying

Contributing
------------

See [docs/contributing.md](./docs/contributing.md).

Dependencies
------------
  * WeeChat 2.2+ http://weechat.org/
  * websocket-client https://pypi.python.org/pypi/websocket-client/
    * Since WeeChat 2.6, Python 3 modules are required, see https://weechat.org/blog/post/2019/07/02/Python-3-by-default
  * Some distributions package WeeChat's plugin functionalities in separate packages.
    Be sure that your WeeChat supports python plugins. Under Debian, install `weechat-python`

Setup
-----

### 1. Install dependencies

**Arch Linux**: `pacman -S python-websocket-client`

**Debian/Ubuntu**: `apt install weechat-python python3-websocket`

**Fedora**: `dnf install python3-websocket-client`

**FreeBSD**: `pkg install py36-websocket-client`

**OpenBSD**: `pkg_add weechat-python py3-websocket-client`

**Other**: `python3 -m pip install websocket-client`

### 2. Install and load wee-slack

#### From the WeeChat script repo

The easiest way to install wee-slack is from inside WeeChat by running:
`/script install slack.py`

This will install and load it and enable automatically loading it when WeeChat
starts.

#### From the GitHub repo

Alternatively, you can download the `wee_slack.py` script from the GitHub repo,
either from the latest release or from the master branch and place it under the
`python/` directory in [the WeeChat data files
directory](https://weechat.org/files/doc/stable/weechat_user.en.html#files_and_directories).

If you use the default XDG directories, this will be
`$XDG_DATA_HOME/weechat/python`, or `~/.local/share/weechat/python` if
`$XDG_DATA_HOME` is not set. If you use the old single directory, it will be
`~/.weechat/python`.

If you use this method and want it to load automatically when WeeChat starts,
you have to create a symlink from the `autoload` directory to the script.

E.g. to install and automatically load the latest version from the master
branch when using `~/.local/share/weechat`:

```
mkdir -p ~/.local/share/weechat/python/autoload
cd ~/.local/share/weechat/python
curl -O https://raw.githubusercontent.com/wee-slack/wee-slack/master/wee_slack.py
ln -s ../wee_slack.py autoload
```

If you already had WeeChat running when installing the script, or if you didn't
enable autoload, you have to [load the
script](https://weechat.org/files/doc/stable/weechat_scripting.en.html#load_script)
by running this inside WeeChat: `/script load wee_slack.py`

### 3. Add your Slack API token(s)

There are two types of tokens that can be used, OAuth tokens and session
tokens. The official way to get a token is to use OAuth. However, this has
several drawbacks, so an alternative way is to pull a session token out of the
web client.

Drawbacks of OAuth tokens:
- If the team is restricting app installations, wee-slack has to be approved by
  an admin.
- For free teams, wee-slack will use one of the ten app slots.
- The subscribe and unsubscribe commands won't work.
- Threads can only be marked as read locally, it won't sync to Slack. This
  means they will be unread again after reloading the script.

Drawbacks of session tokens:
- These tokens can't be revoked, so be careful not to loose them.
- They are not officially supported, and may stop working at any time.

#### Get a token with OAuth

Log in to Slack:

```
/slack register
```

This command prints a link you should open in your browser to authorize WeeChat
with Slack. If the page shows a different team than the one you want to add,
you can change the team in the top right corner of the page.

Once you've accomplished this, the page will show a command which you should
run in WeeChat. The command is of the form:

```
/slack register <code>
```

Note that this will store your token in plain text in the
`plugins.var.python.slack.slack_api_token` option. See "Optional: Secure the
tokens" below for how to secure it.

Your Slack team is now added, and you can complete the setup by reloading the
wee-slack script.

```
/python reload slack
```

Note that by default GitHub Pages will see a temporary code used to create your
token (but not the token itself). If you're worried about this, you can use the
`-nothirdparty` option, though the process will be a bit less user friendly.

#### Get a session token

1. Open and sign into the [Slack customization page](https://my.slack.com/customize). Check that you end up on the correct team.
2. Open the developer console (`Ctrl+Shift+J`/`Cmd+Opt+J` in Chrome and `Ctrl+Shift+K`/`Cmd+Opt+K` in Firefox).
3. Paste and run this code: `window.prompt("Session token:", TS.boot_data.api_token)`
4. A prompt with the token will appear. Copy the token.
5. In the developer console go to Application in Chrome or Storage in Firefox.
6. Expand Cookies and click on the domain.
7. Find the cookie named `d` and copy the value.
8. Return to WeeChat and run `/slack register <token>:<cookie>`.
9. Reload the script with `/python reload slack`.

Note that this will store your token in plain text in the
`plugins.var.python.slack.slack_api_token` option. See "Optional: Secure the
tokens" below for how to secure it.

Note that if you log in or out of any teams in your browser, the cookie will be
invalidated, and you will have to update it.

Note that in some cases it may be necessary to include the `d-s` cookie as
well. If so, you can supply it in this format `<token>:d=<d_cookie>;d-s=<d-s_cookie>`.

If you use Chrome or Firefox, you can run the `extract_token_from_browser.py`
script to get the tokens and cookies for all the teams you're logged into:

```
./extract_token_from_browser.py <browser>
```

(Note this script requires the Plyvel, PyCryptodome and SecretStorage libraries for Chrome and may require the python-snappy library for Firefox.)

#### Optional: Connecting to multiple teams

You can run the register command multiple times to connect to multiple teams.
If you set the token option yourself, you should separate the tokens with
commas.

```
/mute /set plugins.var.python.slack.slack_api_token <token1>,<token2>,<token3>
```

The `/mute` prefix is to prevent "Option changed ..." from being printed to the
core buffer, so your token is not logged in your buffer logs.

#### Optional: Secure the tokens

The tokens you add will be stored as plain text in the option
`plugins.var.python.slack.slack_api_token`. If you don't want to store your API
token in plain text you can use the secure features of WeeChat:

```
/secure passphrase this is a super secret password
/secure set slack_token <YOUR_SLACK_TOKEN>
/set plugins.var.python.slack.slack_api_token ${sec.data.slack_token}
```

Note that you will have to move your tokens manually from
`plugins.var.python.slack.slack_api_token` to the secure variable after each
time you run `/slack register <code>`.

Commands and options
--------------------

For the available options see [docs/Options.md](docs/Options.md) or run this command:
```
/set slack
```

Most options require that you reload the script with `/python reload slack`
after changing it to take effect.

For the available commands see [docs/Commands.md](docs/Commands.md) or run this command:
```
/slack help
```

In addition to the commands listed with `/slack help`, most normal IRC
commands, like `/join`, `/part`, `/query`, `/msg`, `/me`, `/topic`, `/away` and
`/whois` work normally. See [WeeChat's
documentation](https://weechat.org/files/doc/stable/weechat_user.en.html) or
`/help <cmd>` if you are unfamiliar with these.

There are also some special messages you can send:

Modify previous message using regex:
```
s/old text/new text/
```

Modify 3rd previous message using regex:
```
3s/old text/new text/
```

The regex also supports the flags `g` for replacing all instances, `i` for
ignoring case, `m` for making `^` and `$` match the start/end of each line and
`s` for making `.` match a newline too. Use them by appending one or more of
them to the regex:
```
s/old text/new text/gi
```

Delete previous message:
```
s///
```

Add a reaction to the nth last message. The number can be omitted and defaults to the last message. The `+` can be replaced with a `-` to remove a reaction instead.
```
3+:smile:
```

To send a command as a normal message instead of performing the action, prefix it with a slash or a space, like so:
```
//slack
 s/a/b/
```

### Threads

Start a new thread on the most recent message The number indicates which message in the buffer to reply to, in reverse time order:
```
/reply 1 here is a threaded reply to the most recent message!
```

Open an existing thread as a channel. The argument is the thread identifier, which is printed in square brackets with every threaded message in a channel:
```
/thread af8
```

To access the last thread in a channel a shorthand is available:
```
/thread
```

Label a thread with a memorable name. The above command will open a channel called af8, but perhaps you want to call it "meetingnotes". To do so, select that buffer and type:
```
/label meetingnotes
```
_Note: labels do not persist once a thread buffer is closed_

### Emoji characters and tab completions of emoji names

To enable rendering of emoji characters and tab completion of emoji names, copy
or symlink the
[`weemoji.json`](https://github.com/wee-slack/wee-slack/blob/master/weemoji.json)
file to your WeeChat config directory (e.g. `~/.local/share/weechat` or
`~/.weechat`). If doing this after starting wee-slack, you will have to reload
it by running `/python reload slack`.

Emoji names can be completed by typing colon and the start of the emoji name
and pressing tab.

### Cursor and mouse mode

The cursor mode and mouse mode can be used to interact with older messages, for editing, deleting, reacting and replying to a message. Mouse mode can be toggled by pressing `Alt`+`m` and cursor mode can be entered by running `/cursor` (see `/help cursor`).

If mouse mode is enabled, the default behavior when right-clicking on a message is to paste its id in the input. It can be used in `/reply`, `s/` substitution/deletion and in `+:emoji:` commands instead of a message number.
It can also be used as an argument to the `/slack linkarchive` command.

In cursor mode, the `M` key achieves the same result (memo: the default for WeeChat is to paste the message with `m`, `M` simply copies the id).
In addition, `R` will prepare a `/reply id` and `D` will delete the message (provided it's yours).
`T` will open the thread associated to a message, equivalent to `/thread id`
`L` will call the `/slack linkarchive` command behind the hood and paste it to the current input.

Please see WeeChat's documentation about [how to use the cursor mode](https://weechat.org/files/doc/stable/weechat_user.en.html#key_bindings_cursor_context) or [adapt the bindings](https://weechat.org/files/doc/stable/weechat_user.en.html#command_weechat_key) to your preference.

Default key bindings:
```
/key bindctxt mouse @chat(python.*):button2 hsignal:slack_mouse
/key bindctxt cursor @chat(python.*):D hsignal:slack_cursor_delete
/key bindctxt cursor @chat(python.*):L hsignal:slack_cursor_linkarchive
/key bindctxt cursor @chat(python.*):M hsignal:slack_cursor_message
/key bindctxt cursor @chat(python.*):R hsignal:slack_cursor_reply
/key bindctxt cursor @chat(python.*):T hsignal:slack_cursor_thread
```

Note that if these keys are already defined, they will not be overwritten by wee-slack. In that case, you will have to define your own key bindings by running the above commands modified to your liking.

hsignals `slack_mouse` and `slack_cursor_message` currently have the same meaning but may be subject to evolutions.

Removing a team
---------------

You may remove a team by removing its token from the dedicated comma-separated list:
```
/set plugins.var.python.slack.slack_api_token "xoxp-XXXXXXXX,xoxp-XXXXXXXX"
```

You can use tab completion after the key to complete the current value. To see
which token belongs to which team, run `/slack teams`.

After removing the token, you have to reload wee-slack with `/python reload slack`.

Optional settings
-----------------

Show typing notification in main bar (slack_typing_notice):
```
/set weechat.bar.status.items [buffer_count],[buffer_plugin],buffer_number+:+buffer_name+{buffer_nicklist_count}+buffer_filter,[hotlist],completion,scroll,slack_typing_notice
```

Show channel name in hotlist after activity
```
/set weechat.look.hotlist_names_level 14
```

FAQ
---

### How do I keep the buffers sorted alphabetically or with a custom order?

Install the script
[autosort.py](https://weechat.org/scripts/source/autosort.py.html/) by running
`/script install autosort.py`. This will keep your buffer list sorted
alphabetically by default. If you want to customize it, run `/help autosort`.

### How do I group the buffers by team in the buffer list?

Run `/set irc.look.server_buffer independent` and install the
[autosort.py](https://weechat.org/scripts/source/autosort.py.html/) script
mentioned in the previous question.

### How can I get system wide notifications for messages?

#### Local notifications on Linux

Use [this trigger](https://github.com/weechat/weechat/wiki/Triggers#show-a-libnotify-desktop-notification-via-notify-send).
You need the `notify-send` command, or alternatively replace it with another
command in the trigger.

#### Local notifications on macOS

Use [the notification_center.py script](https://weechat.org/scripts/source/notification_center.py.html/). You can install it with `/script install notification_center.py`.

#### Remote notifications

There are many scripts in the [scripts repo](https://weechat.org/scripts/tag/notify/)
for various use cases. Note that not all may work with wee-slack, so you will
have to test them.

### How do I send messages with multiple lines?

With WeeChat >= 4.0.0 this is supported out of the box. You can either press
Alt+Enter to insert a line break, or paste something containing multiple lines.

For older versions of WeeChat, continue reading the next section.

#### For WeeChat < 4.0.0

You have to install a script to be able to send multiple lines, e.g. the
`multiline.pl` script with: `/script install multiline.pl`

By default it will wait for one second after you press enter, and if you type
another character in that period, it will insert the character on a newline,
and if you don't type anything it will send the message. If you rather want to
use a separate key to insert a newline, and have the enter key send the message
immediately, you can run these commands:

```
/set plugins.var.perl.multiline.magic_paste_only on
/key bind meta-ctrl-M /input insert \n
```

This will bind meta-enter (which is usually alt-enter) to insert the newline.
Replace `meta-ctrl-M` with something else if you want to use a different key
combination.

The `multiline.pl` script will also let you edit pasted text which incudes
newlines before you send the message. If this is not working, you may try to
run the commands below. At least in the `kitty` terminal, it won't work by
default, but should work after running these commands:

```
/set plugins.var.perl.multiline.weechat_paste_fix "off"
/key bind ctrl-J /input magic_enter
```

You may also want to disable WeeChat's paste prompt, since that is not necessary
when using `multiline.pl`:

```
/set weechat.look.paste_max_lines -1
```

Known issues
------------

Not all issues are listed here (see
[issues](https://github.com/wee-slack/wee-slack/issues) for all), but these are
some noteworthy:

- If you set `background_load_all_history` to `false`:
  - Channels will not be shown as unread when wee-slack loads, even if there
    are unread messages. Messages which arrive after wee-slack has loaded
    however will mark the channel as unread.
  - If messages arrive while the connection to Slack is lost (e.g. during
    suspend), they will not appear in the hotlist.
- If you use an OAuth token or a legacy token instead of a session token:
  - Threads can only be marked as read locally, it won't sync to Slack. This
    means they will be unread again after reloading the script.

Debugging
---------

To help debugging you can enable debugging output about what wee-slack is doing
by enabling debug mode and changing debug level (between 0 and 5, default is 3,
decrease to increase logging and vice versa). Enabling this will open a new
buffer `slack-debug` where the messages are printed. Enable it and change level
by running:

```
/set plugins.var.python.slack.debug_mode on
/set plugins.var.python.slack.debug_level 0
```

You can also dump all the JSON responses received from the API in
`/tmp/weeslack-debug/`. This requires a script reload after enabling. Enable it
with:

```
/set plugins.var.python.slack.record_events true
/python reload slack
```

Support
-------

wee-slack is provided without any warranty whatsoever, but you are welcome to ask questions in #wee-slack on [Libera.Chat](https://libera.chat/).

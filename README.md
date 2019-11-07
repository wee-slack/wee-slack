wee-slack
=========

A WeeChat native client for Slack.com. Provides supplemental features only available in the web/mobile clients such as: synchronizing read markers, typing notification, threads (and more)! Connects via the Slack API, and maintains a persistent websocket for notification of events.

![animated screenshot](https://github.com/wee-slack/wee-slack/raw/master/docs/slack.gif)

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

Dependencies
------------
  * WeeChat 1.3+ http://weechat.org/
  * websocket-client https://pypi.python.org/pypi/websocket-client/
    * Since WeeChat 2.6, Python 3 modules are required, see https://weechat.org/blog/post/2019/07/02/Python-3-by-default
  * Some distributions package weechat's plugin functionalities in separate packages.
    Be sure that your weechat supports python plugins. Under Debian, install `weechat-python`

Setup
-----

### 1. Install dependencies

**Arch Linux**: `pacman -S python-websocket-client`

**Debian/Ubuntu**: `apt install weechat-python python-websocket`. If using weechat 2.6 or newer, run `apt install weechat-python python3-websocket` instead.

**Fedora**: `dnf install python3-websocket-client`

**FreeBSD**: `pkg install py36-websocket-client`

**OpenBSD**: `pkg_add weechat-python py3-websocket-client`

**Other**: `pip install websocket-client`

Note for **macOS**: If you installed weechat with Homebrew, you will have to locate the python runtime environment used.
If `--with-python@2` was used, you should use: `sudo /usr/local/opt/python@2/bin/pip2 install websocket_client`

### 2. Download wee\_slack.py to ~/.weechat/python

If you don't want wee\_slack to start automatically when weechat starts, you can skip the last command.

```
mkdir -p ~/.weechat/python/autoload
cd ~/.weechat/python
curl -O https://raw.githubusercontent.com/wee-slack/wee-slack/master/wee_slack.py
ln -s ../wee_slack.py autoload
```

### 3. Start WeeChat
```
weechat
```

**NOTE:** If weechat is already running, the script can be loaded using `/python load wee_slack.py`.

### 4. Add your Slack API key(s)

Log in to Slack:

```
/slack register
```

This command prints a link you should open in your browser to authorize WeeChat
with Slack. Once you've accomplished this, copy the "code" portion of the URL in
the browser and pass it to this command:

```
/slack register [CODE_FROM_URL]
```

Your Slack team is now added, and you can complete setup by restarting the
wee-slack script.

```
/python reload slack
```

Alternatively, you can click the "Request token" button at the
[Slack legacy token page](https://api.slack.com/custom-integrations/legacy-tokens),
and paste it directly into your settings:

```
/set plugins.var.python.slack.slack_api_token [YOUR_SLACK_TOKEN]
```

If you don't want to store your API token in plaintext you can use the secure features of weechat:

```
/secure passphrase this is a super secret password
/secure set slack_token [YOUR_SLACK_TOKEN]
/set plugins.var.python.slack.slack_api_token ${sec.data.slack_token}
```

#### Optional: Connecting to multiple teams

You can run the register command multiple times to connect to multiple teams.
If you set the token yourself, you can use the above command with multiple
tokens separated by commas.

```
/set plugins.var.python.slack.slack_api_token [token1],[token2],[token3]
```

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

### Emoji tab completions

To enable tab completion of emojis, copy or symlink the `weemoji.json` file to
your weechat config directory (e.g. `~/.weechat`). If doing this after starting
wee-slack, you will have to reload it by running `/python reload slack`. Then
append `|%(emoji)` to the `weechat.completion.default_template` config option,
e.g. like this:

```
/set weechat.completion.default_template "%(nicks)|%(irc_channels)|%(emoji)"
```

### User group tab completions
To enable tab completions for usergroups append `|%(usergroups)`
```
/set weechat.completion.default_template "%(nicks)|%(irc_channels)|%(usergroups)"
```
The usergroup will appear in the same formats as nicks like the following `@marketing` where marketing is the handle

### Cursor and mouse mode

The cursor mode and mouse mode can be used to interact with older messages, for editing, deleting, reacting and replying to a message. Mouse mode can be toggled by pressing `Alt`+`m` and cursor mode can be entered by running `/cursor` (see `/help cursor`).

If mouse mode is enabled, the default behavior when right-clicking on a message is to paste its id in the input. It can be used in `/reply`, `s/` substitution/deletion and in `+:emoji:` commands instead of a message number.
It can also be used as an argument to the `/slack linkarchive` command.

In cursor mode, the `M` key achieves the same result (memo: the default for weechat is to paste the message with `m`, `M` simply copies the id).
In addition, `R` will prepare a `/reply id` and `D` will delete the message (provided it's yours).
`T` will open the thread associated to a message, equivalent to `/thread id`
`L` will call the `/slack linkarchive` command behind the hood and paste it to the current input.

Please see weechat's documentation about [how to use the cursor mode](https://weechat.org/files/doc/stable/weechat_user.en.html#key_bindings_cursor_context) or [adapt the bindings](https://weechat.org/files/doc/stable/weechat_user.en.html#command_weechat_key) to your preference.

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

### How do I send messages with multiple lines?

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

You may also want to disable weechats paste prompt, since that is not necessary
when using `multiline.pl`:

```
/set weechat.look.paste_max_lines -1
```

Known issues
------------

Not all issues are listed here (see
[issues](https://github.com/wee-slack/wee-slack/issues) for all), but these are
some noteworthy:

- For channels initially created as a public channel, but later converted to a private channel:
  - Which messages that has been read is not synced to Slack.
  - If the option `background_load_all_history` is false, the channel will not
    be shown as unread when wee-slack loads, even if there are unread messages.
    Messages which arrive after wee-slack has loaded however will mark the
    channel as unread.
  - The option `thread_messages_in_channel` is only working for messages which
    arrive after the channel history has been loaded.

Development
-----------

To run the tests, create a virtualenv and pip install from the `requirements.txt`. Then `pytest` to run them locally.

Enable debug mode and change debug level (default 3, decrease to increase logging and vice versa):

```
/set plugins.var.python.slack.debug_mode on
/set plugins.var.python.slack.debug_level 2
```

Dump the JSON responses in `/tmp/weeslack-debug/`. Requires a script reload.
```
/set plugins.var.python.slack.record_events true
```

Support
-------

wee-slack is provided without any warranty whatsoever, but you are welcome to ask questions in #wee-slack on freenode.

wee-slack
=========

A WeeChat native client for Slack.com. Provides supplemental features only available in the web/mobile clients such as: synchronizing read markers, typing notification, threads (and more)! Connects via the Slack API, and maintains a persistent websocket for notification of events.

![animated screenshot](https://github.com/wee-slack/wee-slack/raw/master/docs/slack.gif)

Features
--------
  * [Threads](#threads) support
  * [Slack Status](#status) support
  * Slash commands (including custom ones)
  * Upload to slack capabilities
  * Emoji reactions
  * Edited messages work just like the official clients, where the original message changes and has (edited) appended.
  * Unfurled urls dont generate a new message, but replace the original with more info as it is received.
  * Regex style message editing (s/oldtext/newtext/)
  * Smarter redraw of dynamic buffer info (much lower CPU %)
  * beta UTF-8 support
  * Doesn't use IRC gateway. Connects directly with Slack via API/Websocket
  * Multiple Teams supported. Just add multiple api tokens separated by commas
  * Replays history automatically during startup. (and sets read marker to the correct position in history)
  * Open channels synchronized with Slack. When you open/close a channel on another client it is reflected in wee-slack
  * Colorized nicks in buffer list when used with buffers.pl
  * Colorized nicks in chat
  * Supports bidirectional slack read notifications for all channels. (never reread the same messages on the web client or other devices).
  * Typing notification, so you can see when others are typing, and they can see when you type. Appears globally for direct messages
  * Away/back status handling
  * Expands/shows metadata for things like tweets/links
  * Displays edited messages (slack.com irc mode currently doesn't show these)
  * *Super fun* debug mode. See what the websocket is saying

In Development
--------------
  * add notification of new versions of wee-slack


Dependencies
------------
  * WeeChat 1.3+ http://weechat.org/
  * websocket-client https://pypi.python.org/pypi/websocket-client/
  * Some distributions package weechat's plugin functionalities in separate packages.
    Be sure that your weechat supports python plugins. Under Debian, install `weechat-python`

Setup
------


#### 0.

wee-slack doesn't use the Slack IRC gateway. If you currently connect via the gateway, you should probably remove the server definition.

```
/server list
    All servers:
        slack
/server del slack
/python reload
```

#### 1. Install dependencies

##### OSX and Linux
```
pip install websocket-client
```

Note: If you installed weechat with Homebrew, you will have to locate the python runtime environment used.
If `--with-python@2` was used, you should use:
```
sudo /usr/local/opt/python@2/bin/pip2 install websocket_client
```

##### FreeBSD
```
pkg install py27-websocket-client py27-six
```

#### 2. copy wee_slack.py to ~/.weechat/python/autoload
```
wget https://raw.githubusercontent.com/wee-slack/wee-slack/master/wee_slack.py
cp wee_slack.py ~/.weechat/python/autoload
```

#### 3. Start WeeChat
```
weechat
```

**NOTE:** If weechat is already running, the script can be loaded using ``/python load python/autoload/wee_slack.py``

#### 4. Add your Slack API key(s)

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
wee-slack plugin.

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

##### Optional: If you would like to connect to multiple groups, use the above command with multiple tokens separated by commas.

```
/set plugins.var.python.slack.slack_api_token [token1],[token2],[token3]
```

### 5. $PROFIT$
```
/save
/python reload
```

Commands
--------

Join a channel:
```
/join [channel]
```

Start a direct chat with someone or multiple users:
```
/query <username>[,<username2>[,<username3>...]]
/slack talk <username>[,<username2>[,<username3>...]]
```

List channels:
```
/slack channels
```

List users:
```
/slack users
```

Close channel/dm:
```
/part
/leave
/close
```

Set yourself away/back:
```
/slack away
/slack back
```

Toggle muting of the current channel:
```
/slack mute
```

List muted channels for the current team:
```
/slack showmuted
```

Modify previous message:
```
s/old text/new text/
```

Modify 3rd previous message:
```
3s/old text/new text/
```

Replace all instances of text in previous message:
```
s/old text/new text/g
```


Delete previous message:
```
s///
```

Add a reaction to the nth last message. The number can be omitted and defaults to the last message. The `+` can be replaced with a `-` to remove a reaction instead.
```
3+:smile:
```

Upload a file to the current slack buffer:
```
/slack upload [file_path]
```

Run a Slack slash command. Simply prepend `/slack slash` to what you'd type in the official clients.:
```
/slack slash /desiredcommand arg1 arg2 arg3
```

To send a command as a normal message instead of performing the action, prefix it with a slash or a space, like so:
```
//slack
 s/a/b/
```

#### Threads

Start a new thread on the most recent message The number indicates which message in the buffer to reply to, in reverse time order:
```
/reply 1 here is a threaded reply to the most recent message!
```

Open an existing thread as a channel. The argument is the thread identifier, which is printed in square brackets with every threaded message in a channel:
```
/thread af8
```

Reply to an existing thread. The second argument is the thread identifier, which is printed in square brackets with every threaded message in a channel:
```
/thread af8 Hello thread!
```

Label a thread with a memorable name. The above command will open a channel called af8, but perhaps you want to call it "meetingnotes". To do so, select that buffer and type:
```
/label meetingnotes
```
_Note: labels do not persist once a thread buffer is closed_

#### Status

Set your Slack status on a given team:
```
/slack status [:emoji:] [Status message]
```

Example:
```
/slack status :ghost: Boo!
```

#### Emoji tab completions

To enable tab completion of emojis, copy or symlink the `weemoji.json` file to your weechat config directory (e.g. `~/.weechat`). Then append `|%(emoji)` to the `weechat.completion.default_template` config option, e.g. like this:

```
/set weechat.completion.default_template "%(nicks)|%(irc_channels)|%(emoji)"
```

Removing a team
---------------

You may remove a team by removing its token from the dedicated comma-separated list:
```
/set plugins.var.python.slack.slack_api_token "xoxp-XXXXXXXX,xoxp-XXXXXXXX"
```

Optional settings
-----------------

Set channel prefix to something other than my-slack-subdomain.slack.com (e.g. when using buffers.pl):
```
/set plugins.var.python.slack.server_aliases "my-slack-subdomain:mysub,other-domain:coolbeans"
```

Show who added each reaction. Makes reactions appear like `[:smile:(@nick1,@nick2)]` instead of `[:smile:2]`.
```
/set plugins.var.python.slack.show_reaction_nicks on
```

Show typing notification in main bar (slack_typing_notice):
```
/set weechat.bar.status.items [buffer_count],[buffer_plugin],buffer_number+:+buffer_name+{buffer_nicklist_count}+buffer_filter,[hotlist],completion,scroll,slack_typing_notice
```

Show channel name in hotlist after activity
```
/set weechat.look.hotlist_names_level 14
```

Development
-----------------

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
--------------

wee-slack is provided without any warranty whatsoever, but you are welcome to ask questions in #wee-slack on freenode.






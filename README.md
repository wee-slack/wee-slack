

wee-slack
=========

**News:**
 The 0.99.1+ has a number of backend changes to make things faster and better. You should use it. :) _(please report bugs in #wee-slack on freenode)_

A WeeChat native client for Slack.com. Provides supplemental features only available in the web/mobile clients such as: synchronizing read markers, typing notification, search, (and more)! Connects via the Slack API, and maintains a persistent websocket for notification of events.

![animated screenshot](https://dl.dropboxusercontent.com/u/566560/slack.gif)

Features
--------
  * **New** Upload to slack capabilities!
  * Emoji reactions!
  * Edited messages work just like the official clients, where the original message changes and has (edited) appended.
  * Unfurled urls dont generate a new message, but replace the original with more info as it is received.
  * Regex style message editing (s/oldtext/newtext/)
  * Caches message history, making startup MUCH faster
  * Smarter redraw of dynamic buffer info (much lower CPU %)
  * beta UTF-8 support
  * Doesn't use IRC gateway. Connects directly with Slack via API/Websocket
  * Multiple Teams supported! Just add multiple api tokens separated by commas
  * Replays history automatically during startup. (and sets read marker to the correct position in history)
  * Open channels synchronized with Slack. When you open/close a channel on another client it is reflected in wee-slack
  * Colorized nicks in buffer list when used with buffers.pl
  * Colorized nicks in chat
  * Supports bidirectional slack read notifications for all channels. (never reread the same messages on the web client or other devices).
  * Typing notification, so you can see when others are typing, and they can see when you type. Appears globally for direct messages
  * Search slack history allows you to do simple searches across all previous slack conversations
  * Away/back status handling
  * Expands/shows metadata for things like tweets/links
  * Displays edited messages (slack.com irc mode currently doesn't show these)

  * *Super fun* debug mode. See what the websocket is saying with `/slack debug`

In Development
--------------
  * fix search
  * add notification of new versions of wee-slack
  * growl notification


Dependencies
------------
  * WeeChat 1.3+ http://weechat.org/
  * websocket-client https://pypi.python.org/pypi/websocket-client/

Setup
------


####0.

wee-slack doesn't use the Slack IRC gateway. If you currently connect via the gateway, you should probably remove the server definition.

```
/server list
    All servers:
        slack
/server del slack
/python reload
```

####1. Install dependencies

##### OSX and Linux
```
pip install websocket-client
```

##### FreeBSD
```
pkg install py27-websocket-client py27-six
```

####2. copy wee_slack.py to ~/.weechat/python/autoload
```
wget https://raw.githubusercontent.com/rawdigits/wee-slack/master/wee_slack.py
cp wee_slack.py ~/.weechat/python/autoload
```

####3. Start WeeChat
```
weechat
```

**NOTE:** If weechat is already running, the script can be loaded using ``/python load python/autoload/wee_slack.py``

####4. Add your Slack API key(s)
```
/set plugins.var.python.slack_extension.slack_api_token [YOUR_SLACK_TOKEN]
```
^^ (find this at https://api.slack.com/web behind the "Generate test tokens" button)

If you don't want to store your API token in plaintext you can use the secure features of weechat:

```
/secure passphrase this is a super secret password
/secure set slack_token [YOUR_SLACK_TOKEN]
/set plugins.var.python.slack_extension.slack_api_token ${sec.data.slack_token}
```

##### Optional: If you would like to connect to multiple groups, use the above command with multiple tokens separated by commas. (NO SPACES)

```
/set plugins.var.python.slack_extension.slack_api_token [token1],[token2],[token3]
```

###5. $PROFIT$
```
/save
/python reload
```

Commands
--------

Join a channel:
```
/join [channel]
/slack join [channel]
```

Start a direct chat with someone:
```
/query [username]
/slack talk [username]
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

Modify previous message *Note: this is not regex, just similar syntax*:
```
s/old text/new text/
```

Delete previous message:
```
s///
```

Add a reaction to the nth last message. The number can be omitted and defaults to the last message. The `+` can be replaced with a `-` to remove a reaction instead.
```
3+:smile:
```

Turn off colorized nicks:
```
/set plugins.var.python.slack_extension.colorize_nicks 0
```

Turn on colorized messages (messages match nick color):
```
/set plugins.var.python.slack_extension.colorize_nicks 1
```

Set channel prefix to something other than my-slack-subdomain.slack.com (e.g. when using buffers.pl):
```
/set plugins.var.python.slack_extension.server_alias.my-slack-subdomain "mysub"
```

Set all read markers to a specific time:
```
/slack setallreadmarkers (time in epoch)
```

Upload a file to the current slack buffer:
```
/slack upload [file_path]
```

Debug mode:
```
/slack debug
```

Optional settings
----------------

Show typing notification in main bar (slack_typing_notice):
```
/set weechat.bar.status.items [buffer_count],[buffer_plugin],buffer_number+:+buffer_name+{buffer_nicklist_count}+buffer_filter,[hotlist],completion,scroll,slack_typing_notice
```

Show channel name in hotlist after activity
```
/set weechat.look.hotlist_names_level 14
```

Support
--------------

wee-slack is provided without any warranty whatsoever, but you are welcome to ask questions in #wee-slack on freenode.






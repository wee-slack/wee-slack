

wee-slack
=========

#Important Update

wee-slack has been refactored, and no longer depends on the Slack IRC gateway. To use this plugin, please disable any IRC connections you have set up for Slack. Once you do this, your existing configuration should work as expected.

```
/server list
    All servers:
        slack
/server del slack
/python reload
```

A WeeChat plugin for Slack.com IRC mode. Provides supplemental features only available in the web/mobile clients such as: synchronizing read markers, typing notification, search, (and more)! Connects via the Slack API, and maintains a persistent websocket for notification of events.

![animated screenshot](https://dl.dropboxusercontent.com/u/566560/slack.gif)

Features
--------
  * **New** Doesn't use IRC gateway. Connects directly with Slack via API/Websocket
  * **New** Multiple Teams supported! Just add multiple api tokens separated by commas
  * **New** Replays history automatically during startup. (and sets read marker to the correct position in history)
  * **New** Open channels synchronized with Slack. When you open/close a channel on another client it is reflected in wee-slack
  * **New** Colorized nicks in buffer list when used with buffers.pl
  * **New** Colorized nicks in chat
  * Supports bidirectional slack read notifications for all channels. (never reread the same messages on the web client or other devices).
  * Typing notification, so you can see when others are typing, and they can see when you type. Appears globally for direct messages
  * Search slack history allows you to do simple searches across all previous slack conversations
  * Away/back status handling
  * Expands/shows metadata for things like tweets/links
  * Displays edited messages (slack.com irc mode currently doesn't show these)

  * *Super fun* debug mode. See what the websocket is saying with `/slack debug`

In Development
--------------
  * cache history pulls
  * fix search
  * add notification of new versions of wee-slack
  * growl notification


Dependencies
------------
  * WeeChat 1.0+ http://weechat.org/ 
  * websocket-client https://pypi.python.org/pypi/websocket-client/

Setup
------

####1. Install websocket-client lib
```
pip install websocket-client
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

####4. Add your Slack API key(s)
```
/set plugins.var.python.slack_extension.slack_api_token (YOUR_SLACK_TOKEN)
```
^^ (find this at https://api.slack.com/#auth)
##### Optional: If you would like to connect to multiple groups, use the above command with multiple tokens separated by commas. (NO SPACES)
    
```
/set plugins.var.python.slack_extension.slack_api_token (token1),(token2),(token3)
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
/slack join [channel]
```

Start a direct chat with someone:
```
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
/close
```

Set yourself away/back:
```
/slack away
/slack back
```

Turn off colorized nicks:
```
/set plugins.var.python.slack_extension.colorize_nicks 0
```

Set all read markers to a specific time:
```
/slack setallreadmarkers (time in epoch)
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

Persistent list of global users on left:
-------------
```
/bar add globalnicklist root left 0 1 @irc.slack.#general:buffer_nicklist
```

Show channel name in hotlist after activity
```
/set weechat.look.hotlist_names_level 14
```






    

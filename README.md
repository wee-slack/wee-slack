


wee-slack
=========

#Update!

Currently testing a branch that supports multiple teams and NO LONGER REQUIRES IRC! To try, just pull the branch called "alpha_features"

    git clone git@github.com:rawdigits/wee-slack.git
    cd wee-slack
    git checkout alpha_features

Notes for alpha (important!):
  * Turn off irc (and disable autoconnect)!
  * Only need to set API Token, all other vars are pulled from Slack
  * new command to join slack channels
    ```/slack join (channel)```

  * new command to open a direct chat
    ```/slack talk (username)```

  * To test multi team, just do:

  ```/set plugins.var.python.slack_extension.slack_api_token (token1),(token2),(token3)```


Alpha Features:
  * Doesn't use IRC gateway. Connects directly with Slack via API/Websocket
  * Multiple Teams supported! Just add multiple api tokens separated by commas
  * Replays history during startup. (and sets read marker to the correct position in history)
  * Open channels synchronized with Slack. When you open/close a channel on another client it is reflected in wee-slack
  * Colorized nicks in buffer list when used with buffers.pl
  * Colorized nicks in chat

In Development:
  * cache history pulls
  * fix search
  * add notification of new versions of wee-slack
  * growl notification


A WeeChat plugin for Slack.com IRC mode. Provides supplemental features only available in the web/mobile clients such as: synchronizing read markers, typing notification, search, (and more)! Connects via the Slack API, and maintains a persistent websocket for notification of events.

![animated screenshot](https://dl.dropboxusercontent.com/u/566560/slack.gif)

#Features

  * Supports bidirectional slack read notifications for all channels. (never reread the same messages on the web client or other devices).
  * Typing notification, so you can see when others are typing, and they can see when you type. Appears globally for direct messages
  * Search slack history allows you to do simple searches across all previous slack conversations
  * Away/back status handling
  * Expands/shows metadata for things like tweets/links
  * Displays edited messages (slack.com irc mode currently doesn't show these)
  * *Super fun* debug mode. See what the websocket is saying with `/slack debug`

#Dependencies

  * WeeChat 1.0+ http://weechat.org/ 

  * websocket-client https://pypi.python.org/pypi/websocket-client/

#Setup

###1. Install websocket-client lib

    pip install websocket-client

###2. copy wee_slack.py to ~/.weechat/python/autoload

    wget https://raw.githubusercontent.com/rawdigits/wee-slack/master/wee_slack.py
    cp wee_slack.py ~/.weechat/python/autoload

###3. Start WeeChat

    weechat

###4. Add a slack as an IRC server in weechat

    /server add slack (YOUR_IRC_SERVER)/6667 -nicks=(YOUR_SLACK_USERNAME) -ssl -ssl_dhkey_size=1 -autoconnect
    (YOUR IRC SERVER is your domain+irc.slack.com, ex: rednu.irc.slack.com)
    /set irc.server.slack.password (YOUR_SLACK_PASSWORD)

###5. Configure the slack plugin


    /set plugins.var.python.slack_extension.slack_api_token (YOUR_SLACK_TOKEN)

^^ (find this at https://api.slack.com/#auth)

    /set plugins.var.python.slack_extension.server (WEECHAT_SERVER_SHORT_NAME)
^^ (find this with `/server list`, probably 'slack')

###6. $PROFIT$
    
    /save
    /python reload
    
#Optional settings (you want this)

##### Show typing notification in main bar (slack_typing_notice)

    /set weechat.bar.status.items [buffer_count],[buffer_plugin],buffer_number+:+buffer_name+{buffer_nicklist_count}+buffer_filter,[hotlist],completion,scroll,slack_typing_notice

##### Hide voice/devoice messages

    /filter add hide_irc_mode_messages * irc_mode *

##### Persistent list of global users on left:

    /bar add globalnicklist root left 0 1 @irc.slack.#general:buffer_nicklist

##### Show channel name in hotlist after activity

    /set weechat.look.hotlist_names_level 14







    

wee-slack
=========

A WeeChat plugin for Slack.com. Synchronizes read markers, provides typing notification, search, and more!


#Dependencies

pip install websocket-client

weechat dev build from May 17 onward (or weechat > 4.4, expected Aug 15, 2014)

#Setup

###1. Add a slack as an IRC server in weechat

    /server add slack (YOUR_IRC_SERVER)/6667 -nicks=(YOUR_SLACK_USERNAME) -ssl -ssl_dhkey_size=1 -autoconnect
    (YOUR IRC SERVER is your domain+irc.slack.com, ex: rednu.irc.slack.com)
    /set irc.server.slack.password (YOUR_SLACK_PASSWORD)

###2. copy wee_slack.py to ~/.weechat/python/autoload

###3. Configure the slack plugin


    /set plugins.var.python.slack_extension.slack_api_token (YOUR_SLACK_TOKEN)
                                                            ^^ (find this at https://api.slack.com/ under Authentication)
    /set plugins.var.python.slack_extension.server (WEECHAT_SERVER_SHORT_NAME)
                                                   ^^ (find this with /server list, probably 'slack')

###4.
    
    /save
    /python reload
    
###5. Optional configuration (you want this)

##### Show typing notification in main bar
    /set weechat.bar.status.items [buffer_count],[buffer_plugin],buffer_number+:+buffer_name+{buffer_nicklist_count}+buffer_filter,[hotlist],completion,scroll,slack_typing_notice

##### Hide voice/devoice messages
    /filter add hide_irc_mode_messages * irc_mode *








    

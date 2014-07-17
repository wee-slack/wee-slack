wee-slack
=========

A WeeChat plugin for Slack.com. Synchronizes read markers, provides typing notification, search, and more!


##Deps:

pip install websocket-client

weechat dev build from May 17 onward (or weechat > 4.4, expected Aug 15, 2014)

##Setup:

#####1. Add a slack as an IRC server in weechat

#####2. copy wee_slack.py to ~/.weechat/python/autoload

#####3. Configure the slack plugin


    /set plugins.var.python.slack_extension.slack_api_token your_slack_token
                                                            ^^ (find this at https://api.slack.com/ under Authentication)
    /set plugins.var.python.slack_extension.server weechat_server_short name
                                                   ^^ (find this with /server list)

#####4.
    
    /save
    /python reload
    

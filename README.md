wee-slack
=========

A WeeChat plugin for Slack.com. Synchronizes read markers, provides typing notification, search, and more!


##Deps:

pip install mechanize

pip install websocket-client

weechat dev build from May 17 onward (or weechat > 4.4, expected Aug 15, 2014)

##Setup:

#####1. Add a slack as an IRC server in weechat

#####2. copy wee_slack.py to ~/.weechat/python/autoload

#####3. Configure the slack plugin

    /set plugins.var.python.slack_extension.domain example.slack.com
    /set plugins.var.python.slack_extension.email your_login_email@yourdomain.com
    /set plugins.var.python.slack_extension.password your_slack_password
    /set plugins.var.python.slack_extension.nick your_slack_nickname
    /set plugins.var.python.slack_extension.server weechat_server_short name
                                                    ^^ (find this with /server list)

#####4.
    
    /save
    /python reload
    

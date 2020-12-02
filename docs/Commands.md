# Commands

These are the commands made available by this script. In In addition to
these commands, most normal IRC commands, like `/join`, `/part`,
`/query`, `/msg`, `/me`, `/topic`, `/away` and `/whois` work normally.
See [WeeChat's
documentation](https://weechat.org/files/doc/stable/weechat_user.en.html)
or `/help <cmd>` if you are unfamiliar with these.

## Available commands:

### away

```
/slack away
```

Sets your status as 'away'.

### back

```
/slack back
```

Sets your status as 'back'.

### channels

```
/slack channels
```

List the channels in the current team.

### create

```
/slack create [-private] <channel_name>
```

Create a public or private channel.

### distracting

```
/slack distracting
```

Add or remove the current channel from distracting channels. You can hide
or unhide these channels with /slack nodistractions.

### help

```
/slack help [command]
```

Print help for /slack commands.

### hide

```
/hide
```

Hide the current channel if it is marked as distracting.

### label

```
/label [-full] <name>|-unset
```

Rename a channel or thread buffer. Note that this is not permanent, it will
only last as long as you keep the buffer and wee-slack open. Changes the
short_name by default, and the name and full_name if you use the -full
option. If you haven't set the short_name explicitly, that will also be
changed when using the -full option. Use the -unset option to set it back
to the default.

### linkarchive

```
/slack linkarchive [message_id]
```

Place a link to the channel or message in the input bar.
Use cursor or mouse mode to get the id.

### mute

```
/slack mute
```

Toggle mute on the current channel.

### nodistractions

```
/slack nodistractions
```

Hide or unhide all channels marked as distracting.

### register

```
/slack register [-nothirdparty] [code/token]
```

Register a Slack team in wee-slack. Call this without any arguments and
follow the instructions to register a new team. If you already have a token
for a team, you can call this with that token to add it.

By default GitHub Pages will see a temporary code used to create your token
(but not the token itself). If you're worried about this, you can use the
-nothirdparty option, though the process will be a bit less user friendly.

### rehistory

```
/rehistory [-remote]
```

Reload the history in the current channel.
With -remote the history will be downloaded again from Slack.

### reply

```
/reply [-alsochannel] [<count/message_id>] <message>
```


When in a channel buffer:
/reply [-alsochannel] <count/message_id> <message>
Reply in a thread on the message. Specify either the message id or a count
upwards to the message from the last message.

When in a thread buffer:
/reply [-alsochannel] <message>
Reply to the current thread.  This can be used to send the reply to the
rest of the channel.

In either case, -alsochannel also sends the reply to the parent channel.

### showmuted

```
/slack showmuted
```

List the muted channels in the current team.

### slash

```
/slack slash /customcommand arg1 arg2 arg3
```

Run a custom slack command.

### status

```
/slack status [<emoji> [<status_message>]|-delete]
```

Lets you set your Slack Status (not to be confused with away/here).
Prints current status if no arguments are given, unsets the status if -delete is given.

### subscribe

```
/slack subscribe <thread>
```

Subscribe to a thread, so that you are alerted to new messages. When in a
thread buffer, you can omit the thread id.

This command only works when using a session token, see the readme: https://github.com/wee-slack/wee-slack#4-add-your-slack-api-tokens

### talk

```
/slack talk <user>[,<user2>[,<user3>...]]
```

Open a chat with the specified user(s).

### teams

```
/slack teams
```

List the connected Slack teams.

### thread

```
/thread [count/message_id]
```

Open the thread for the message.
If no message id is specified the last thread in channel will be opened.

### unsubscribe

```
/slack unsubscribe <thread>
```

Unsubscribe from a thread that has been previously subscribed to, so that
you are not alerted to new messages. When in a thread buffer, you can omit
the thread id.

This command only works when using a session token, see the readme: https://github.com/wee-slack/wee-slack#4-add-your-slack-api-tokens

### upload

```
/slack upload <filename>
```

Uploads a file to the current buffer.

### usergroups

```
/slack usergroups [handle]
```

List the usergroups in the current team
If handle is given show the members in the usergroup

### users

```
/slack users
```

List the users in the current team.


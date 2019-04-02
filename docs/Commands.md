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

### distracting

```
/slack distracting
```

Add or remove the current channel from distracting channels. You can hide
or unhide these channels with /slack nodistractions.

### help

```
/slack help
```

Print help for /slack commands.

### hide

```
/hide
```

Hide the current channel if it is marked as distracting.

### label

```
/label <name>
```

Rename a thread buffer. Note that this is not permanent. It will only last
as long as you keep the buffer and wee-slack open.

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
/slack register
```

Register a Slack team in wee-slack.

### rehistory

```
/rehistory
```

Reload the history in the current channel.

### reply

```
/reply <count/message_id> <text>
```

Reply in a thread on the message. Specify either the message id
or a count upwards to the message from the last message.

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
/slack status [emoji [status_message]]
```

Lets you set your Slack Status (not to be confused with away/here).

### talk

```
/slack talk <user>[,<user2>[,<user3>...]]
```

Open a chat with the specified user(s).

### thread

```
/thread [message_id]
```

Open the thread for the message.
If no message id is specified the last thread in channel will be opened.

### upload

```
/slack upload <filename>
```

Uploads a file to the current buffer.

### users

```
/slack users
```

List the users in the current team.


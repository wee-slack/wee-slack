#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals

from textwrap import dedent
import wee_slack

cmds = wee_slack.EventRouter().cmds
options = wee_slack.PluginConfig.default_settings

with open('docs/Commands.md', 'w') as file_cmds:
    file_cmds.write(dedent("""
        # Commands

        These are the commands made available by this script. In In addition to
        these commands, most normal IRC commands, like `/join`, `/part`,
        `/query`, `/msg`, `/me`, `/topic`, `/away` and `/whois` work normally.
        See [WeeChat's
        documentation](https://weechat.org/files/doc/stable/weechat_user.en.html)
        or `/help <cmd>` if you are unfamiliar with these.

        ## Available commands:

        """).lstrip())

    for name, cmd in sorted(cmds.items()):
        doc = dedent(cmd.__doc__ or '').strip()
        command, helptext = doc.split('\n', 1)
        file_cmds.write(dedent("""
            ### {}

            ```
            {}
            ```

            {}

            """).lstrip().format(name, command, helptext))

with open('docs/Options.md', 'w') as file_options:
    file_options.write(dedent("""
        # Options

        You can set these options by using:

        ```
        /set plugins.var.python.slack.option_name value
        ```

        You can also see all the options and set them them interactively by running `/fset slack`.

        Note that the default value will be shown as an empty string in weechat.
        The actual default values are listed below.

        Most options require that you reload the script with `/python reload
        slack` after changing it to take effect.

        ## Available options:

        """).lstrip())

    for name, option in sorted(options.items()):
        file_options.write(dedent("""
            ### {}

            **Default:** `{}`

            **Description:** {}

            """).lstrip().format(name, option.default, option.desc))

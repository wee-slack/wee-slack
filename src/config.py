"""Configuration management for wee-slack."""

from __future__ import unicode_literals

import collections

from src.debug import create_slack_debug_buffer,set_debug_level
from src.weechat_wrapper import w

Setting = collections.namedtuple('Setting', ['default', 'desc'])

class PluginConfig(object):
    # Default settings.
    # These are, initially, each a (default, desc) tuple; the former is the
    # default value of the setting, in the (string) format that weechat
    # expects, and the latter is the user-friendly description of the setting.
    # At __init__ time these values are extracted, the description is used to
    # set or update the setting description for use with /help, and the default
    # value is used to set the default for any settings not already defined.
    # Following this procedure, the keys remain the same, but the values are
    # the real (python) values of the settings.
    default_settings = {
        'background_load_all_history': Setting(
            default='false',
            desc='Load history for each channel in the background as soon as it'
            ' opens, rather than waiting for the user to look at it.'),
        'channel_name_typing_indicator': Setting(
            default='true',
            desc='Change the prefix of a channel from # to > when someone is'
            ' typing in it. Note that this will (temporarily) affect the sort'
            ' order if you sort buffers by name rather than by number.'),
        'colorize_private_chats': Setting(
            default='false',
            desc='Whether to use nick-colors in DM windows.'),
        'debug_mode': Setting(
            default='false',
            desc='Open a dedicated buffer for debug messages and start logging'
            ' to it. How verbose the logging is depends on log_level.'),
        'debug_level': Setting(
            default='3',
            desc='Show only this level of debug info (or higher) when'
            ' debug_mode is on. Lower levels -> more messages.'),
        'distracting_channels': Setting(
            default='',
            desc='List of channels to hide.'),
        'group_name_prefix': Setting(
            default='&',
            desc='The prefix of buffer names for groups (private channels).'),
        'map_underline_to': Setting(
            default='_',
            desc='When sending underlined text to slack, use this formatting'
            ' character for it. The default ("_") sends it as italics. Use'
            ' "*" to send bold instead.'),
        'never_away': Setting(
            default='false',
            desc='Poke Slack every five minutes so that it never marks you "away".'),
        'record_events': Setting(
            default='false',
            desc='Log all traffic from Slack to disk as JSON.'),
        'render_bold_as': Setting(
            default='bold',
            desc='When receiving bold text from Slack, render it as this in weechat.'),
        'render_italic_as': Setting(
            default='italic',
            desc='When receiving bold text from Slack, render it as this in weechat.'
            ' If your terminal lacks italic support, consider using "underline" instead.'),
        'send_typing_notice': Setting(
            default='true',
            desc='Alert Slack users when you are typing a message in the input bar '
            '(Requires reload)'),
        'server_aliases': Setting(
            default='',
            desc='A comma separated list of `subdomain:alias` pairs. The alias'
            ' will be used instead of the actual name of the slack (in buffer'
            ' names, logging, etc). E.g `work:no_fun_allowed` would make your'
            ' work slack show up as `no_fun_allowed` rather than `work.slack.com`.'),
        'short_buffer_names': Setting(
            default='false',
            desc='Use `foo.#channel` rather than `foo.slack.com.#channel` as the'
            ' internal name for Slack buffers. Overrides server_aliases.'),
        'show_reaction_nicks': Setting(
            default='false',
            desc='Display the name of the reacting user(s) alongside each reactji.'),
        'slack_api_token': Setting(
            default='INSERT VALID KEY HERE!',
            desc='List of Slack API tokens, one per Slack instance you want to'
            ' connect to. See the README for details on how to get these.'),
        'slack_timeout': Setting(
            default='20000',
            desc='How long (ms) to wait when communicating with Slack.'),
        'switch_buffer_on_join': Setting(
            default='true',
            desc='When /joining a channel, automatically switch to it as well.'),
        'thread_suffix_color': Setting(
            default='lightcyan',
            desc='Color to use for the [thread: XXX] suffix on messages that'
            ' have threads attached to them.'),
        'unfurl_ignore_alt_text': Setting(
            default='false',
            desc='When displaying ("unfurling") links to channels/users/etc,'
            ' ignore the "alt text" present in the message and instead use the'
            ' canonical name of the thing being linked to.'),
        'unfurl_auto_link_display': Setting(
            default='both',
            desc='When displaying ("unfurling") links to channels/users/etc,'
            ' determine what is displayed when the text matches the url'
            ' without the protocol. This happens when Slack automatically'
            ' creates links, e.g. from words separated by dots or email'
            ' addresses. Set it to "text" to only display the text written by'
            ' the user, "url" to only display the url or "both" (the default)'
            ' to display both.'),
        'unhide_buffers_with_activity': Setting(
            default='false',
            desc='When activity occurs on a buffer, unhide it even if it was'
            ' previously hidden (whether by the user or by the'
            ' distracting_channels setting).'),
    }

    # Set missing settings to their defaults. Load non-missing settings from
    # weechat configs.
    def __init__(self):
        self.settings = {}
        # Set all descriptions, replace the values in the dict with the
        # default setting value rather than the (setting,desc) tuple.
        # Use items() rather than iteritems() so we don't need to worry about
        # invalidating the iterator.
        for key, (default, desc) in self.default_settings.items():
            w.config_set_desc_plugin(key, desc)
            self.settings[key] = default

        # Migrate settings from old versions of Weeslack...
        self.migrate()
        # ...and then set anything left over from the defaults.
        for key, default in self.settings.iteritems():
            if not w.config_get_plugin(key):
                w.config_set_plugin(key, default)
        self.config_changed(None, None, None)

    def __str__(self):
        return "".join([x + "\t" + str(self.settings[x]) + "\n" for x in self.settings.keys()])

    def config_changed(self, data, key, value):
        for key in self.settings:
            self.settings[key] = self.fetch_setting(key)
        if self.debug_mode:
            set_debug_level(self.debug_level)
            create_slack_debug_buffer()
        return w.WEECHAT_RC_OK

    def fetch_setting(self, key):
        if hasattr(self, 'get_' + key):
            try:
                return getattr(self, 'get_' + key)(key)
            except:
                return self.settings[key]
        else:
            # Most settings are on/off, so make get_boolean the default
            return self.get_boolean(key)

    def __getattr__(self, key):
        return self.settings[key]

    def get_boolean(self, key):
        return w.config_string_to_boolean(w.config_get_plugin(key))

    def get_string(self, key):
        return w.config_get_plugin(key)

    def get_int(self, key):
        return int(w.config_get_plugin(key))

    def is_default(self, key):
        default = self.default_settings.get(key).default
        return w.config_get_plugin(key) == default

    get_debug_level = get_int
    get_group_name_prefix = get_string
    get_map_underline_to = get_string
    get_render_bold_as = get_string
    get_render_italic_as = get_string
    get_slack_timeout = get_int
    get_thread_suffix_color = get_string
    get_unfurl_auto_link_display = get_string

    def get_distracting_channels(self, key):
        return [x.strip() for x in w.config_get_plugin(key).split(',')]

    def get_server_aliases(self, key):
        alias_list = w.config_get_plugin(key)
        if len(alias_list) > 0:
            return dict(item.split(":") for item in alias_list.split(","))

    def get_slack_api_token(self, key):
        token = w.config_get_plugin("slack_api_token")
        if token.startswith('${sec.data'):
            return w.string_eval_expression(token, {}, {}, {})
        else:
            return token

    def migrate(self):
        """
        This is to migrate the extension name from slack_extension to slack
        """
        if not w.config_get_plugin("migrated"):
            for k in self.settings.keys():
                if not w.config_is_set_plugin(k):
                    p = w.config_get("plugins.var.python.slack_extension.{}".format(k))
                    data = w.config_string(p)
                    if data != "":
                        w.config_set_plugin(k, data)
            w.config_set_plugin("migrated", "true")



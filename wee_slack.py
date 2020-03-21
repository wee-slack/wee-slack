# Copyright (c) 2014-2016 Ryan Huber <rhuber@gmail.com>
# Copyright (c) 2015-2018 Tollef Fog Heen <tfheen@err.no>
# Copyright (c) 2015-2020 Trygve Aaberge <trygveaa@gmail.com>
# Released under the MIT license.

from __future__ import print_function, unicode_literals

from collections import OrderedDict
from datetime import date, datetime, timedelta
from functools import partial, wraps
from io import StringIO
from itertools import chain, count, islice

import errno
import textwrap
import time
import json
import hashlib
import os
import re
import sys
import traceback
import collections
import ssl
import random
import socket
import string

# Prevent websocket from using numpy (it's an optional dependency). We do this
# because numpy causes python (and thus weechat) to crash when it's reloaded.
# See https://github.com/numpy/numpy/issues/11925
sys.modules["numpy"] = None

from websocket import ABNF, create_connection, WebSocketConnectionClosedException

try:
    basestring     # Python 2
    unicode
    str = unicode
except NameError:  # Python 3
    basestring = unicode = str

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

try:
    from json import JSONDecodeError
except:
    JSONDecodeError = ValueError

# hack to make tests possible.. better way?
try:
    import weechat
except ImportError:
    pass

SCRIPT_NAME = "slack"
SCRIPT_AUTHOR = "Ryan Huber <rhuber@gmail.com>"
SCRIPT_VERSION = "2.4.0"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Extends weechat for typing notification/search/etc on slack.com"
REPO_URL = "https://github.com/wee-slack/wee-slack"

BACKLOG_SIZE = 200
SCROLLBACK_SIZE = 500

RECORD_DIR = "/tmp/weeslack-debug"

SLACK_API_TRANSLATOR = {
    "channel": {
        "history": "channels.history",
        "join": "conversations.join",
        "leave": "conversations.leave",
        "mark": "channels.mark",
        "info": "channels.info",
    },
    "im": {
        "history": "im.history",
        "join": "conversations.open",
        "leave": "conversations.close",
        "mark": "im.mark",
    },
    "mpim": {
        "history": "mpim.history",
        "join": "mpim.open",  # conversations.open lacks unread_count_display
        "leave": "conversations.close",
        "mark": "mpim.mark",
        "info": "groups.info",
    },
    "group": {
        "history": "groups.history",
        "join": "conversations.join",
        "leave": "conversations.leave",
        "mark": "groups.mark",
        "info": "groups.info"
    },
    "private": {
        "history": "conversations.history",
        "join": "conversations.join",
        "leave": "conversations.leave",
        "mark": "conversations.mark",
        "info": "conversations.info",
    },
    "shared": {
        "history": "conversations.history",
        "join": "conversations.join",
        "leave": "conversations.leave",
        "mark": "channels.mark",
        "info": "conversations.info",
    },
    "thread": {
        "history": None,
        "join": None,
        "leave": None,
        "mark": None,
    }


}

###### Decorators have to be up here


def slack_buffer_or_ignore(f):
    """
    Only run this function if we're in a slack buffer, else ignore
    """
    @wraps(f)
    def wrapper(data, current_buffer, *args, **kwargs):
        if current_buffer not in EVENTROUTER.weechat_controller.buffers:
            return w.WEECHAT_RC_OK
        return f(data, current_buffer, *args, **kwargs)
    return wrapper


def slack_buffer_required(f):
    """
    Only run this function if we're in a slack buffer, else print error
    """
    @wraps(f)
    def wrapper(data, current_buffer, *args, **kwargs):
        if current_buffer not in EVENTROUTER.weechat_controller.buffers:
            command_name = f.__name__.replace('command_', '', 1)
            w.prnt('', 'slack: command "{}" must be executed on slack buffer'.format(command_name))
            return w.WEECHAT_RC_ERROR
        return f(data, current_buffer, *args, **kwargs)
    return wrapper


def utf8_decode(f):
    """
    Decode all arguments from byte strings to unicode strings. Use this for
    functions called from outside of this script, e.g. callbacks from weechat.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        return f(*decode_from_utf8(args), **decode_from_utf8(kwargs))
    return wrapper


NICK_GROUP_HERE = "0|Here"
NICK_GROUP_AWAY = "1|Away"
NICK_GROUP_EXTERNAL = "2|External"

sslopt_ca_certs = {}
if hasattr(ssl, "get_default_verify_paths") and callable(ssl.get_default_verify_paths):
    ssl_defaults = ssl.get_default_verify_paths()
    if ssl_defaults.cafile is not None:
        sslopt_ca_certs = {'ca_certs': ssl_defaults.cafile}

EMOJI = {}
EMOJI_WITH_SKIN_TONES_REVERSE = {}

###### Unicode handling


def encode_to_utf8(data):
    if sys.version_info.major > 2:
        return data
    elif isinstance(data, unicode):
        return data.encode('utf-8')
    if isinstance(data, bytes):
        return data
    elif isinstance(data, collections.Mapping):
        return type(data)(map(encode_to_utf8, data.items()))
    elif isinstance(data, collections.Iterable):
        return type(data)(map(encode_to_utf8, data))
    else:
        return data


def decode_from_utf8(data):
    if sys.version_info.major > 2:
        return data
    elif isinstance(data, bytes):
        return data.decode('utf-8')
    if isinstance(data, unicode):
        return data
    elif isinstance(data, collections.Mapping):
        return type(data)(map(decode_from_utf8, data.items()))
    elif isinstance(data, collections.Iterable):
        return type(data)(map(decode_from_utf8, data))
    else:
        return data


class WeechatWrapper(object):
    def __init__(self, wrapped_class):
        self.wrapped_class = wrapped_class

    # Helper method used to encode/decode method calls.
    def wrap_for_utf8(self, method):
        def hooked(*args, **kwargs):
            result = method(*encode_to_utf8(args), **encode_to_utf8(kwargs))
            # Prevent wrapped_class from becoming unwrapped
            if result == self.wrapped_class:
                return self
            return decode_from_utf8(result)
        return hooked

    # Encode and decode everything sent to/received from weechat. We use the
    # unicode type internally in wee-slack, but has to send utf8 to weechat.
    def __getattr__(self, attr):
        orig_attr = self.wrapped_class.__getattribute__(attr)
        if callable(orig_attr):
            return self.wrap_for_utf8(orig_attr)
        else:
            return decode_from_utf8(orig_attr)

    # Ensure all lines sent to weechat specifies a prefix. For lines after the
    # first, we want to disable the prefix, which is done by specifying a space.
    def prnt_date_tags(self, buffer, date, tags, message):
        message = message.replace("\n", "\n \t")
        return self.wrap_for_utf8(self.wrapped_class.prnt_date_tags)(buffer, date, tags, message)


class ProxyWrapper(object):
    def __init__(self):
        self.proxy_name = w.config_string(w.config_get('weechat.network.proxy_curl'))
        self.proxy_string = ""
        self.proxy_type = ""
        self.proxy_address = ""
        self.proxy_port = ""
        self.proxy_user = ""
        self.proxy_password = ""
        self.has_proxy = False

        if self.proxy_name:
            self.proxy_string = "weechat.proxy.{}".format(self.proxy_name)
            self.proxy_type = w.config_string(w.config_get("{}.type".format(self.proxy_string)))
            if self.proxy_type == "http":
                self.proxy_address = w.config_string(w.config_get("{}.address".format(self.proxy_string)))
                self.proxy_port = w.config_integer(w.config_get("{}.port".format(self.proxy_string)))
                self.proxy_user = w.config_string(w.config_get("{}.username".format(self.proxy_string)))
                self.proxy_password = w.config_string(w.config_get("{}.password".format(self.proxy_string)))
                self.has_proxy = True
            else:
                w.prnt("", "\nWarning: weechat.network.proxy_curl is set to {} type (name : {}, conf string : {}). Only HTTP proxy is supported.\n\n".format(self.proxy_type, self.proxy_name, self.proxy_string))

    def curl(self):
        if not self.has_proxy:
            return ""

        if self.proxy_user and self.proxy_password:
            user = "{}:{}@".format(self.proxy_user, self.proxy_password)
        else:
            user = ""

        if self.proxy_port:
            port = ":{}".format(self.proxy_port)
        else:
            port = ""

        return "-x{}{}{}".format(user, self.proxy_address, port)


##### Helpers


def colorize_string(color, string, reset_color='reset'):
    if color:
        return w.color(color) + string + w.color(reset_color)
    else:
        return string


def print_error(message, buffer='', warning=False):
    prefix = 'Warning' if warning else 'Error'
    w.prnt(buffer, '{}{}: {}'.format(w.prefix('error'), prefix, message))


def token_for_print(token):
    return '{}...{}'.format(token[:15], token[-10:])


def format_exc_tb():
    return decode_from_utf8(traceback.format_exc())


def format_exc_only():
    etype, value, _ = sys.exc_info()
    return ''.join(decode_from_utf8(traceback.format_exception_only(etype, value)))


def get_nick_color(nick):
    info_name_prefix = "irc_" if int(weechat_version) < 0x1050000 else ""
    return w.info_get(info_name_prefix + "nick_color_name", nick)


def get_thread_color(thread_id):
    if config.color_thread_suffix == 'multiple':
        return get_nick_color(thread_id)
    else:
        return config.color_thread_suffix


def sha1_hex(s):
    return hashlib.sha1(s.encode('utf-8')).hexdigest()


def get_functions_with_prefix(prefix):
    return {name[len(prefix):]: ref for name, ref in globals().items()
            if name.startswith(prefix)}


def handle_socket_error(exception, team, caller_name):
    if not (isinstance(exception, WebSocketConnectionClosedException) or
            exception.errno in (errno.EPIPE, errno.ECONNRESET, errno.ETIMEDOUT)):
        raise

    w.prnt(team.channel_buffer,
            'Lost connection to slack team {} (on {}), reconnecting.'.format(
                team.domain, caller_name))
    dbg('Socket failed on {} with exception:\n{}'.format(
        caller_name, format_exc_tb()), level=5)
    team.set_disconnected()


EMOJI_NAME_REGEX = re.compile(':([^: ]+):')
EMOJI_REGEX_STRING = '[\U00000080-\U0010ffff]+'


def regex_match_to_emoji(match, include_name=False):
    emoji = match.group(1)
    full_match = match.group()
    char = EMOJI.get(emoji, full_match)
    if include_name and char != full_match:
        return '{} ({})'.format(char, full_match)
    return char


def replace_string_with_emoji(text):
    if config.render_emoji_as_string == 'both':
        return EMOJI_NAME_REGEX.sub(
            partial(regex_match_to_emoji, include_name=True),
            text,
        )
    elif config.render_emoji_as_string:
        return text
    return EMOJI_NAME_REGEX.sub(regex_match_to_emoji, text)


def replace_emoji_with_string(text):
    return EMOJI_WITH_SKIN_TONES_REVERSE.get(text, text)


###### New central Event router

class EventRouter(object):

    def __init__(self):
        """
        complete
        Eventrouter is the central hub we use to route:
        1) incoming websocket data
        2) outgoing http requests and incoming replies
        3) local requests
        It has a recorder that, when enabled, logs most events
        to the location specified in RECORD_DIR.
        """
        self.queue = []
        self.slow_queue = []
        self.slow_queue_timer = 0
        self.teams = {}
        self.subteams = {}
        self.context = {}
        self.weechat_controller = WeechatController(self)
        self.previous_buffer = ""
        self.reply_buffer = {}
        self.cmds = get_functions_with_prefix("command_")
        self.proc = get_functions_with_prefix("process_")
        self.handlers = get_functions_with_prefix("handle_")
        self.local_proc = get_functions_with_prefix("local_process_")
        self.shutting_down = False
        self.recording = False
        self.recording_path = "/tmp"
        self.handle_next_hook = None
        self.handle_next_hook_interval = -1

    def record(self):
        """
        complete
        Toggles the event recorder and creates a directory for data if enabled.
        """
        self.recording = not self.recording
        if self.recording:
            if not os.path.exists(RECORD_DIR):
                os.makedirs(RECORD_DIR)

    def record_event(self, message_json, file_name_field, subdir=None):
        """
        complete
        Called each time you want to record an event.
        message_json is a json in dict form
        file_name_field is the json key whose value you want to be part of the file name
        """
        now = time.time()
        if subdir:
            directory = "{}/{}".format(RECORD_DIR, subdir)
        else:
            directory = RECORD_DIR
        if not os.path.exists(directory):
            os.makedirs(directory)
        mtype = message_json.get(file_name_field, 'unknown')
        f = open('{}/{}-{}.json'.format(directory, now, mtype), 'w')
        f.write("{}".format(json.dumps(message_json)))
        f.close()

    def store_context(self, data):
        """
        A place to store data and vars needed by callback returns. We need this because
        weechat's "callback_data" has a limited size and weechat will crash if you exceed
        this size.
        """
        identifier = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(40))
        self.context[identifier] = data
        dbg("stored context {} {} ".format(identifier, data.url))
        return identifier

    def retrieve_context(self, identifier):
        """
        A place to retrieve data and vars needed by callback returns. We need this because
        weechat's "callback_data" has a limited size and weechat will crash if you exceed
        this size.
        """
        return self.context.get(identifier)

    def delete_context(self, identifier):
        """
        Requests can span multiple requests, so we may need to delete this as a last step
        """
        if identifier in self.context:
            del self.context[identifier]

    def shutdown(self):
        """
        complete
        This toggles shutdown mode. Shutdown mode tells us not to
        talk to Slack anymore. Without this, typing /quit will trigger
        a race with the buffer close callback and may result in you
        leaving every slack channel.
        """
        self.shutting_down = not self.shutting_down

    def register_team(self, team):
        """
        complete
        Adds a team to the list of known teams for this EventRouter.
        """
        if isinstance(team, SlackTeam):
            self.teams[team.get_team_hash()] = team
        else:
            raise InvalidType(type(team))

    def reconnect_if_disconnected(self):
        for team in self.teams.values():
            time_since_last_ping = time.time() - team.last_ping_time
            time_since_last_pong = time.time() - team.last_pong_time
            if team.connected and time_since_last_ping < 5 and time_since_last_pong > 30:
                w.prnt(team.channel_buffer,
                        'Lost connection to slack team {} (no pong), reconnecting.'.format(
                            team.domain))
                team.set_disconnected()
            if not team.connected:
                team.connect()
                dbg("reconnecting {}".format(team))

    @utf8_decode
    def receive_ws_callback(self, team_hash, fd):
        """
        This is called by the global method of the same name.
        It is triggered when we have incoming data on a websocket,
        which needs to be read. Once it is read, we will ensure
        the data is valid JSON, add metadata, and place it back
        on the queue for processing as JSON.
        """
        team = self.teams[team_hash]
        while True:
            try:
                # Read the data from the websocket associated with this team.
                opcode, data = team.ws.recv_data(control_frame=True)
            except ssl.SSLWantReadError:
                # No more data to read at this time.
                return w.WEECHAT_RC_OK
            except (WebSocketConnectionClosedException, socket.error) as e:
                handle_socket_error(e, team, 'receive')
                return w.WEECHAT_RC_OK

            if opcode == ABNF.OPCODE_PONG:
                team.last_pong_time = time.time()
                return w.WEECHAT_RC_OK
            elif opcode != ABNF.OPCODE_TEXT:
                return w.WEECHAT_RC_OK

            message_json = json.loads(data.decode('utf-8'))
            message_json["wee_slack_metadata_team"] = team
            if self.recording:
                self.record_event(message_json, 'type', 'websocket')
            self.receive(message_json)
        return w.WEECHAT_RC_OK

    @utf8_decode
    def receive_httprequest_callback(self, data, command, return_code, out, err):
        """
        complete
        Receives the result of an http request we previously handed
        off to weechat (weechat bundles libcurl). Weechat can fragment
        replies, so it buffers them until the reply is complete.
        It is then populated with metadata here so we can identify
        where the request originated and route properly.
        """
        request_metadata = self.retrieve_context(data)
        dbg("RECEIVED CALLBACK with request of {} id of {} and  code {} of length {}".format(request_metadata.request, request_metadata.response_id, return_code, len(out)))
        if return_code == 0:
            if len(out) > 0:
                if request_metadata.response_id not in self.reply_buffer:
                    self.reply_buffer[request_metadata.response_id] = StringIO()
                self.reply_buffer[request_metadata.response_id].write(out)
                try:
                    j = json.loads(self.reply_buffer[request_metadata.response_id].getvalue())
                except:
                    pass
                    # dbg("Incomplete json, awaiting more", True)
                try:
                    j["wee_slack_process_method"] = request_metadata.request_normalized
                    if self.recording:
                        self.record_event(j, 'wee_slack_process_method', 'http')
                    j["wee_slack_request_metadata"] = request_metadata
                    self.reply_buffer.pop(request_metadata.response_id)
                    self.receive(j)
                    self.delete_context(data)
                except:
                    dbg("HTTP REQUEST CALLBACK FAILED", True)
                    pass
            # We got an empty reply and this is weird so just ditch it and retry
            else:
                dbg("length was zero, probably a bug..")
                self.delete_context(data)
                self.receive(request_metadata)
        elif return_code == -1:
            if request_metadata.response_id not in self.reply_buffer:
                self.reply_buffer[request_metadata.response_id] = StringIO()
            self.reply_buffer[request_metadata.response_id].write(out)
        else:
            self.reply_buffer.pop(request_metadata.response_id, None)
            self.delete_context(data)
            if request_metadata.request.startswith('rtm.'):
                retry_text = ('retrying' if request_metadata.should_try() else
                        'will not retry after too many failed attempts')
                w.prnt('', ('Failed connecting to slack team with token {}, {}. ' +
                        'If this persists, try increasing slack_timeout. Error: {}')
                        .format(token_for_print(request_metadata.token), retry_text, err))
                dbg('rtm.start failed with return_code {}. stack:\n{}'
                        .format(return_code, ''.join(traceback.format_stack())), level=5)
                self.receive(request_metadata)
        return w.WEECHAT_RC_OK

    def receive(self, dataobj):
        """
        complete
        Receives a raw object and places it on the queue for
        processing. Object must be known to handle_next or
        be JSON.
        """
        dbg("RECEIVED FROM QUEUE")
        self.queue.append(dataobj)

    def receive_slow(self, dataobj):
        """
        complete
        Receives a raw object and places it on the slow queue for
        processing. Object must be known to handle_next or
        be JSON.
        """
        dbg("RECEIVED FROM QUEUE")
        self.slow_queue.append(dataobj)

    def handle_next(self):
        """
        complete
        Main handler of the EventRouter. This is called repeatedly
        via callback to drain events from the queue. It also attaches
        useful metadata and context to events as they are processed.
        """
        wanted_interval = 100
        if len(self.slow_queue) > 0 or len(self.queue) > 0:
            wanted_interval = 10
        if self.handle_next_hook is None or wanted_interval != self.handle_next_hook_interval:
            if self.handle_next_hook:
                w.unhook(self.handle_next_hook)
            self.handle_next_hook = w.hook_timer(wanted_interval, 0, 0, "handle_next", "")
            self.handle_next_hook_interval = wanted_interval


        if len(self.slow_queue) > 0 and ((self.slow_queue_timer + 1) < time.time()):
            dbg("from slow queue", 0)
            self.queue.append(self.slow_queue.pop())
            self.slow_queue_timer = time.time()
        if len(self.queue) > 0:
            j = self.queue.pop(0)
            # Reply is a special case of a json reply from websocket.
            kwargs = {}
            if isinstance(j, SlackRequest):
                if j.should_try():
                    if j.retry_ready():
                        local_process_async_slack_api_request(j, self)
                    else:
                        self.slow_queue.append(j)
                else:
                    dbg("Max retries for Slackrequest")

            else:

                if "reply_to" in j:
                    dbg("SET FROM REPLY")
                    function_name = "reply"
                elif "type" in j:
                    dbg("SET FROM type")
                    function_name = j["type"]
                elif "wee_slack_process_method" in j:
                    dbg("SET FROM META")
                    function_name = j["wee_slack_process_method"]
                else:
                    dbg("SET FROM NADA")
                    function_name = "unknown"

                request = j.get("wee_slack_request_metadata")
                if request:
                    team = request.team
                    channel = request.channel
                    metadata = request.metadata
                else:
                    team = j.get("wee_slack_metadata_team")
                    channel = None
                    metadata = {}

                if team:
                    if "channel" in j:
                        channel_id = j["channel"]["id"] if type(j["channel"]) == dict else j["channel"]
                        channel = team.channels.get(channel_id, channel)
                    if "user" in j:
                        user_id = j["user"]["id"] if type(j["user"]) == dict else j["user"]
                        metadata['user'] = team.users.get(user_id)

                dbg("running {}".format(function_name))
                if function_name.startswith("local_") and function_name in self.local_proc:
                    self.local_proc[function_name](j, self, team, channel, metadata)
                elif function_name in self.proc:
                    self.proc[function_name](j, self, team, channel, metadata)
                elif function_name in self.handlers:
                    self.handlers[function_name](j, self, team, channel, metadata)
                else:
                    dbg("Callback not implemented for event: {}".format(function_name))


def handle_next(data, remaining_calls):
    try:
        EVENTROUTER.handle_next()
    except:
        if config.debug_mode:
            traceback.print_exc()
        else:
            pass
    return w.WEECHAT_RC_OK


class WeechatController(object):
    """
    Encapsulates our interaction with weechat
    """

    def __init__(self, eventrouter):
        self.eventrouter = eventrouter
        self.buffers = {}
        self.previous_buffer = None
        self.buffer_list_stale = False

    def iter_buffers(self):
        for b in self.buffers:
            yield (b, self.buffers[b])

    def register_buffer(self, buffer_ptr, channel):
        """
        complete
        Adds a weechat buffer to the list of handled buffers for this EventRouter
        """
        if isinstance(buffer_ptr, basestring):
            self.buffers[buffer_ptr] = channel
        else:
            raise InvalidType(type(buffer_ptr))

    def unregister_buffer(self, buffer_ptr, update_remote=False, close_buffer=False):
        """
        complete
        Adds a weechat buffer to the list of handled buffers for this EventRouter
        """
        channel = self.buffers.get(buffer_ptr)
        if channel:
            channel.destroy_buffer(update_remote)
            del self.buffers[buffer_ptr]
            if close_buffer:
                w.buffer_close(buffer_ptr)

    def get_channel_from_buffer_ptr(self, buffer_ptr):
        return self.buffers.get(buffer_ptr)

    def get_all(self, buffer_ptr):
        return self.buffers

    def get_previous_buffer_ptr(self):
        return self.previous_buffer

    def set_previous_buffer(self, data):
        self.previous_buffer = data

    def check_refresh_buffer_list(self):
        return self.buffer_list_stale and self.last_buffer_list_update + 1 < time.time()

    def set_refresh_buffer_list(self, setting):
        self.buffer_list_stale = setting

###### New Local Processors


def local_process_async_slack_api_request(request, event_router):
    """
    complete
    Sends an API request to Slack. You'll need to give this a well formed SlackRequest object.
    DEBUGGING!!! The context here cannot be very large. Weechat will crash.
    """
    if not event_router.shutting_down:
        weechat_request = 'url:{}'.format(request.request_string())
        weechat_request += '&nonce={}'.format(''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(4)))
        params = {'useragent': 'wee_slack {}'.format(SCRIPT_VERSION)}
        request.tried()
        context = event_router.store_context(request)
        # TODO: let flashcode know about this bug - i have to 'clear' the hashtable or retry requests fail
        w.hook_process_hashtable('url:', params, config.slack_timeout, "", context)
        w.hook_process_hashtable(weechat_request, params, config.slack_timeout, "receive_httprequest_callback", context)

###### New Callbacks


@utf8_decode
def ws_ping_cb(data, remaining_calls):
    for team in EVENTROUTER.teams.values():
        if team.ws and team.connected:
            try:
                team.ws.ping()
                team.last_ping_time = time.time()
            except (WebSocketConnectionClosedException, socket.error) as e:
                handle_socket_error(e, team, 'ping')
    return w.WEECHAT_RC_OK


@utf8_decode
def reconnect_callback(*args):
    EVENTROUTER.reconnect_if_disconnected()
    return w.WEECHAT_RC_OK


@utf8_decode
def buffer_closing_callback(signal, sig_type, data):
    """
    Receives a callback from weechat when a buffer is being closed.
    """
    EVENTROUTER.weechat_controller.unregister_buffer(data, True, False)
    return w.WEECHAT_RC_OK


@utf8_decode
def buffer_input_callback(signal, buffer_ptr, data):
    """
    incomplete
    Handles everything a user types in the input bar. In our case
    this includes add/remove reactions, modifying messages, and
    sending messages.
    """
    eventrouter = eval(signal)
    channel = eventrouter.weechat_controller.get_channel_from_buffer_ptr(buffer_ptr)
    if not channel:
        return w.WEECHAT_RC_ERROR

    def get_id(message_id):
        if not message_id:
            return 1
        elif message_id[0] == "$":
            return message_id[1:]
        else:
            return int(message_id)

    message_id_regex = r"(\d*|\$[0-9a-fA-F]{3,})"
    reaction = re.match(r"^{}(\+|-)(:(.+):|{})\s*$".format(message_id_regex, EMOJI_REGEX_STRING), data)
    substitute = re.match("^{}s/".format(message_id_regex), data)
    if reaction:
        emoji_match = reaction.group(4) or reaction.group(3)
        emoji = replace_emoji_with_string(emoji_match)
        if reaction.group(2) == "+":
            channel.send_add_reaction(get_id(reaction.group(1)), emoji)
        elif reaction.group(2) == "-":
            channel.send_remove_reaction(get_id(reaction.group(1)), emoji)
    elif substitute:
        msg_id = get_id(substitute.group(1))
        try:
            old, new, flags = re.split(r'(?<!\\)/', data)[1:]
        except ValueError:
            pass
        else:
            # Replacement string in re.sub() is a string, not a regex, so get
            # rid of escapes.
            new = new.replace(r'\/', '/')
            old = old.replace(r'\/', '/')
            channel.edit_nth_previous_message(msg_id, old, new, flags)
    else:
        if data.startswith(('//', ' ')):
            data = data[1:]
        channel.send_message(data)
        # this is probably wrong channel.mark_read(update_remote=True, force=True)
    return w.WEECHAT_RC_OK


# Workaround for supporting multiline messages. It intercepts before the input
# callback is called, as this is called with the whole message, while it is
# normally split on newline before being sent to buffer_input_callback
def input_text_for_buffer_cb(data, modifier, current_buffer, string):
    if current_buffer not in EVENTROUTER.weechat_controller.buffers:
        return string
    message = decode_from_utf8(string)
    if not message.startswith("/") and "\n" in message:
        buffer_input_callback("EVENTROUTER", current_buffer, message)
        return ""
    return string


@utf8_decode
def buffer_switch_callback(signal, sig_type, data):
    """
    Every time we change channels in weechat, we call this to:
    1) set read marker 2) determine if we have already populated
    channel history data 3) set presence to active
    """
    eventrouter = eval(signal)

    prev_buffer_ptr = eventrouter.weechat_controller.get_previous_buffer_ptr()
    # this is to see if we need to gray out things in the buffer list
    prev = eventrouter.weechat_controller.get_channel_from_buffer_ptr(prev_buffer_ptr)
    if prev:
        prev.mark_read()

    new_channel = eventrouter.weechat_controller.get_channel_from_buffer_ptr(data)
    if new_channel:
        if not new_channel.got_history:
            new_channel.get_history()
        set_own_presence_active(new_channel.team)

    eventrouter.weechat_controller.set_previous_buffer(data)
    return w.WEECHAT_RC_OK


@utf8_decode
def buffer_list_update_callback(data, somecount):
    """
    incomplete
    A simple timer-based callback that will update the buffer list
    if needed. We only do this max 1x per second, as otherwise it
    uses a lot of cpu for minimal changes. We use buffer short names
    to indicate typing via "#channel" <-> ">channel" and
    user presence via " name" <-> "+name".
    """
    eventrouter = eval(data)

    for b in eventrouter.weechat_controller.iter_buffers():
        b[1].refresh()
#    buffer_list_update = True
#    if eventrouter.weechat_controller.check_refresh_buffer_list():
#        # gray_check = False
#        # if len(servers) > 1:
#        #    gray_check = True
#        eventrouter.weechat_controller.set_refresh_buffer_list(False)
    return w.WEECHAT_RC_OK


def quit_notification_callback(signal, sig_type, data):
    stop_talking_to_slack()
    return w.WEECHAT_RC_OK


@utf8_decode
def typing_notification_cb(data, signal, current_buffer):
    msg = w.buffer_get_string(current_buffer, "input")
    if len(msg) > 8 and msg[0] != "/":
        global typing_timer
        now = time.time()
        if typing_timer + 4 < now:
            channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer)
            if channel and channel.type != "thread":
                identifier = channel.identifier
                request = {"type": "typing", "channel": identifier}
                channel.team.send_to_websocket(request, expect_reply=False)
                typing_timer = now
    return w.WEECHAT_RC_OK


@utf8_decode
def typing_update_cb(data, remaining_calls):
    w.bar_item_update("slack_typing_notice")
    return w.WEECHAT_RC_OK


@utf8_decode
def slack_never_away_cb(data, remaining_calls):
    if config.never_away:
        for team in EVENTROUTER.teams.values():
            set_own_presence_active(team)
    return w.WEECHAT_RC_OK


@utf8_decode
def typing_bar_item_cb(data, item, current_window, current_buffer, extra_info):
    """
    Privides a bar item indicating who is typing in the current channel AND
    why is typing a DM to you globally.
    """
    typers = []
    current_channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer)

    # first look for people typing in this channel
    if current_channel:
        # this try is mostly becuase server buffers don't implement is_someone_typing
        try:
            if current_channel.type != 'im' and current_channel.is_someone_typing():
                typers += current_channel.get_typing_list()
        except:
            pass

    # here is where we notify you that someone is typing in DM
    # regardless of which buffer you are in currently
    for team in EVENTROUTER.teams.values():
        for channel in team.channels.values():
            if channel.type == "im":
                if channel.is_someone_typing():
                    typers.append("D/" + channel.slack_name)
                pass

    typing = ", ".join(typers)
    if typing != "":
        typing = colorize_string(config.color_typing_notice, "typing: " + typing)

    return typing


@utf8_decode
def away_bar_item_cb(data, item, current_window, current_buffer, extra_info):
    channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer)
    if not channel:
        return ''

    if channel.team.is_user_present(channel.team.myidentifier):
        return ''
    else:
        away_color = w.config_string(w.config_get('weechat.color.item_away'))
        if channel.team.my_manual_presence == 'away':
            return colorize_string(away_color, 'manual away')
        else:
            return colorize_string(away_color, 'auto away')


@utf8_decode
def channel_completion_cb(data, completion_item, current_buffer, completion):
    """
    Adds all channels on all teams to completion list
    """
    current_channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer)
    should_include_channel = lambda channel: channel.active and channel.type in ['channel', 'group', 'private', 'shared']

    other_teams = [team for team in EVENTROUTER.teams.values() if not current_channel or team != current_channel.team]
    for team in other_teams:
        for channel in team.channels.values():
            if should_include_channel(channel):
                w.hook_completion_list_add(completion, channel.name, 0, w.WEECHAT_LIST_POS_SORT)

    if current_channel:
        for channel in sorted(current_channel.team.channels.values(), key=lambda channel: channel.name, reverse=True):
            if should_include_channel(channel):
                w.hook_completion_list_add(completion, channel.name, 0, w.WEECHAT_LIST_POS_BEGINNING)

        if should_include_channel(current_channel):
            w.hook_completion_list_add(completion, current_channel.name, 0, w.WEECHAT_LIST_POS_BEGINNING)
    return w.WEECHAT_RC_OK


@utf8_decode
def dm_completion_cb(data, completion_item, current_buffer, completion):
    """
    Adds all dms/mpdms on all teams to completion list
    """
    for team in EVENTROUTER.teams.values():
        for channel in team.channels.values():
            if channel.active and channel.type in ['im', 'mpim']:
                w.hook_completion_list_add(completion, channel.name, 0, w.WEECHAT_LIST_POS_SORT)
    return w.WEECHAT_RC_OK


@utf8_decode
def nick_completion_cb(data, completion_item, current_buffer, completion):
    """
    Adds all @-prefixed nicks to completion list
    """
    current_channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer)
    if current_channel is None or current_channel.members is None:
        return w.WEECHAT_RC_OK

    base_command = w.hook_completion_get_string(completion, "base_command")
    if base_command in ['invite', 'msg', 'query', 'whois']:
        members = current_channel.team.members
    else:
        members = current_channel.members

    for member in members:
        user = current_channel.team.users.get(member)
        if user and not user.deleted:
            w.hook_completion_list_add(completion, user.name, 1, w.WEECHAT_LIST_POS_SORT)
            w.hook_completion_list_add(completion, "@" + user.name, 1, w.WEECHAT_LIST_POS_SORT)
    return w.WEECHAT_RC_OK


@utf8_decode
def emoji_completion_cb(data, completion_item, current_buffer, completion):
    """
    Adds all :-prefixed emoji to completion list
    """
    current_channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer)
    if current_channel is None:
        return w.WEECHAT_RC_OK

    base_word = w.hook_completion_get_string(completion, "base_word")
    if ":" not in base_word:
        return w.WEECHAT_RC_OK
    prefix = base_word.split(":")[0] + ":"

    for emoji in current_channel.team.emoji_completions:
        w.hook_completion_list_add(completion, prefix + emoji + ":", 0, w.WEECHAT_LIST_POS_SORT)
    return w.WEECHAT_RC_OK


@utf8_decode
def thread_completion_cb(data, completion_item, current_buffer, completion):
    """
    Adds all $-prefixed thread ids to completion list
    """
    current_channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer)
    if current_channel is None or not hasattr(current_channel, 'hashed_messages'):
        return w.WEECHAT_RC_OK

    threads = current_channel.hashed_messages.items()
    for thread_id, message_ts in sorted(threads, key=lambda item: item[1]):
        message = current_channel.messages.get(message_ts)
        if message and message.number_of_replies():
            w.hook_completion_list_add(completion, "$" + thread_id, 0, w.WEECHAT_LIST_POS_BEGINNING)
    return w.WEECHAT_RC_OK


@utf8_decode
def topic_completion_cb(data, completion_item, current_buffer, completion):
    """
    Adds topic for current channel to completion list
    """
    current_channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer)
    if current_channel is None:
        return w.WEECHAT_RC_OK

    topic = current_channel.render_topic()
    channel_names = [channel.name for channel in current_channel.team.channels.values()]
    if topic.split(' ', 1)[0] in channel_names:
        topic = '{} {}'.format(current_channel.name, topic)

    w.hook_completion_list_add(completion, topic, 0, w.WEECHAT_LIST_POS_SORT)
    return w.WEECHAT_RC_OK


@utf8_decode
def usergroups_completion_cb(data, completion_item, current_buffer, completion):
    """
    Adds all @-prefixed usergroups to completion list
    """
    current_channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer)
    if current_channel is None:
        return w.WEECHAT_RC_OK

    subteam_handles = [subteam.handle for subteam in current_channel.team.subteams.values()]
    for group in subteam_handles + ["@channel", "@everyone", "@here"]:
        w.hook_completion_list_add(completion, group, 1, w.WEECHAT_LIST_POS_SORT)
    return w.WEECHAT_RC_OK


@utf8_decode
def complete_next_cb(data, current_buffer, command):
    """Extract current word, if it is equal to a nick, prefix it with @ and
    rely on nick_completion_cb adding the @-prefixed versions to the
    completion lists, then let Weechat's internal completion do its
    thing
    """
    current_channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer)
    if not hasattr(current_channel, 'members') or current_channel is None or current_channel.members is None:
        return w.WEECHAT_RC_OK

    line_input = w.buffer_get_string(current_buffer, "input")
    current_pos = w.buffer_get_integer(current_buffer, "input_pos") - 1
    input_length = w.buffer_get_integer(current_buffer, "input_length")

    word_start = 0
    word_end = input_length
    # If we're on a non-word, look left for something to complete
    while current_pos >= 0 and line_input[current_pos] != '@' and not line_input[current_pos].isalnum():
        current_pos = current_pos - 1
    if current_pos < 0:
        current_pos = 0
    for l in range(current_pos, 0, -1):
        if line_input[l] != '@' and not line_input[l].isalnum():
            word_start = l + 1
            break
    for l in range(current_pos, input_length):
        if not line_input[l].isalnum():
            word_end = l
            break
    word = line_input[word_start:word_end]

    for member in current_channel.members:
        user = current_channel.team.users.get(member)
        if user and user.name == word:
            # Here, we cheat.  Insert a @ in front and rely in the @
            # nicks being in the completion list
            w.buffer_set(current_buffer, "input", line_input[:word_start] + "@" + line_input[word_start:])
            w.buffer_set(current_buffer, "input_pos", str(w.buffer_get_integer(current_buffer, "input_pos") + 1))
            return w.WEECHAT_RC_OK_EAT
    return w.WEECHAT_RC_OK


def script_unloaded():
    stop_talking_to_slack()
    return w.WEECHAT_RC_OK


def stop_talking_to_slack():
    """
    complete
    Prevents a race condition where quitting closes buffers
    which triggers leaving the channel because of how close
    buffer is handled
    """
    EVENTROUTER.shutdown()
    for team in EVENTROUTER.teams.values():
        team.ws.shutdown()
    return w.WEECHAT_RC_OK

##### New Classes


class SlackRequest(object):
    """
    Encapsulates a Slack api request. Valuable as an object that we can add to the queue and/or retry.
    makes a SHA of the requst url and current time so we can re-tag this on the way back through.
    """

    def __init__(self, team, request, post_data=None, channel=None, metadata=None, retries=3, token=None):
        if team is None and token is None:
            raise ValueError("Both team and token can't be None")
        self.team = team
        self.request = request
        self.post_data = post_data if post_data else {}
        self.channel = channel
        self.metadata = metadata if metadata else {}
        self.retries = retries
        self.token = token if token else team.token
        self.tries = 0
        self.start_time = time.time()
        self.request_normalized = re.sub(r'\W+', '', request)
        self.domain = 'api.slack.com'
        self.post_data['token'] = self.token
        self.url = 'https://{}/api/{}?{}'.format(self.domain, self.request, urlencode(encode_to_utf8(self.post_data)))
        self.params = {'useragent': 'wee_slack {}'.format(SCRIPT_VERSION)}
        self.response_id = sha1_hex('{}{}'.format(self.url, self.start_time))

    def __repr__(self):
        return ("SlackRequest(team={}, request='{}', post_data={}, retries={}, token='{}', "
                "tries={}, start_time={})").format(self.team, self.request, self.post_data,
                        self.retries, token_for_print(self.token), self.tries, self.start_time)

    def request_string(self):
        return "{}".format(self.url)

    def tried(self):
        self.tries += 1
        self.response_id = sha1_hex("{}{}".format(self.url, time.time()))

    def should_try(self):
        return self.tries < self.retries

    def retry_ready(self):
        return (self.start_time + (self.tries**2)) < time.time()


class SlackSubteam(object):
   """
   Represents a slack group or subteam
   """

   def __init__(self, originating_team_id, is_member, **kwargs):
       self.handle = '@{}'.format(kwargs['handle'])
       self.identifier = kwargs['id']
       self.name = kwargs['name']
       self.description = kwargs.get('description')
       self.team_id = originating_team_id
       self.is_member = is_member

   def __repr__(self):
       return "Name:{} Identifier:{}".format(self.name, self.identifier)

   def __eq__(self, compare_str):
       return compare_str == self.identifier


class SlackTeam(object):
    """
    incomplete
    Team object under which users and channels live.. Does lots.
    """

    def __init__(self, eventrouter, token, team_hash, websocket_url, team_info, subteams,  nick, myidentifier, my_manual_presence, users, bots, channels, **kwargs):
        self.identifier = team_info["id"]
        self.active = True
        self.team_hash = team_hash
        self.ws_url = websocket_url
        self.connected = False
        self.connecting_rtm = False
        self.connecting_ws = False
        self.ws = None
        self.ws_counter = 0
        self.ws_replies = {}
        self.last_ping_time = 0
        self.last_pong_time = time.time()
        self.eventrouter = eventrouter
        self.token = token
        self.team = self
        self.subteams = subteams
        self.team_info = team_info
        self.subdomain = team_info["domain"]
        self.domain = self.subdomain + ".slack.com"
        self.preferred_name = self.domain
        self.nick = nick
        self.myidentifier = myidentifier
        self.my_manual_presence = my_manual_presence
        try:
            if self.channels:
                for c in channels.keys():
                    if not self.channels.get(c):
                        self.channels[c] = channels[c]
        except:
            self.channels = channels
        self.users = users
        self.bots = bots
        self.name = self.domain
        self.channel_buffer = None
        self.got_history = True
        self.create_buffer()
        self.set_muted_channels(kwargs.get('muted_channels', ""))
        self.set_highlight_words(kwargs.get('highlight_words', ""))
        for c in self.channels.keys():
            channels[c].set_related_server(self)
            channels[c].check_should_open()
        # Last step is to make sure my nickname is the set color
        self.users[self.myidentifier].force_color(w.config_string(w.config_get('weechat.color.chat_nick_self')))
        # This highlight step must happen after we have set related server
        self.load_emoji_completions()
        self.type = "team"

    def __repr__(self):
        return "domain={} nick={}".format(self.subdomain, self.nick)

    def __eq__(self, compare_str):
         return compare_str == self.token or compare_str == self.domain or compare_str == self.subdomain

    @property
    def members(self):
        return self.users.keys()

    def load_emoji_completions(self):
        self.emoji_completions = list(EMOJI.keys())
        if self.emoji_completions:
            s = SlackRequest(self, "emoji.list")
            self.eventrouter.receive(s)

    def add_channel(self, channel):
        self.channels[channel["id"]] = channel
        channel.set_related_server(self)

    def generate_usergroup_map(self):
        return {s.handle: s.identifier for s in self.subteams.values()}

    def create_buffer(self):
        if not self.channel_buffer:
            alias = config.server_aliases.get(self.subdomain)
            if alias:
                self.preferred_name = alias
            elif config.short_buffer_names:
                self.preferred_name = self.subdomain
            else:
                self.preferred_name = self.domain
            self.channel_buffer = w.buffer_new(self.preferred_name, "buffer_input_callback", "EVENTROUTER", "", "")
            self.eventrouter.weechat_controller.register_buffer(self.channel_buffer, self)
            w.buffer_set(self.channel_buffer, "localvar_set_type", 'server')
            w.buffer_set(self.channel_buffer, "localvar_set_nick", self.nick)
            w.buffer_set(self.channel_buffer, "localvar_set_server", self.preferred_name)
            self.buffer_merge()

    def buffer_merge(self, config_value=None):
        if not config_value:
            config_value = w.config_string(w.config_get('irc.look.server_buffer'))
        if config_value == 'merge_with_core':
            w.buffer_merge(self.channel_buffer, w.buffer_search_main())
        else:
            w.buffer_unmerge(self.channel_buffer, 0)

    def destroy_buffer(self, update_remote):
        pass

    def set_muted_channels(self, muted_str):
        self.muted_channels = {x for x in muted_str.split(',') if x}
        for channel in self.channels.values():
            channel.set_highlights()

    def set_highlight_words(self, highlight_str):
        self.highlight_words = {x for x in highlight_str.split(',') if x}
        for channel in self.channels.values():
            channel.set_highlights()

    def formatted_name(self, **kwargs):
        return self.domain

    def buffer_prnt(self, data, message=False):
        tag_name = "team_message" if message else "team_info"
        w.prnt_date_tags(self.channel_buffer, SlackTS().major, tag(tag_name), data)

    def send_message(self, message, subtype=None, request_dict_ext={}):
        w.prnt("", "ERROR: Sending a message in the team buffer is not supported")

    def find_channel_by_members(self, members, channel_type=None):
        for channel in self.channels.values():
            if channel.get_members() == members and (
                    channel_type is None or channel.type == channel_type):
                return channel

    def get_channel_map(self):
        return {v.name: k for k, v in self.channels.items()}

    def get_username_map(self):
        return {v.name: k for k, v in self.users.items()}

    def get_team_hash(self):
        return self.team_hash

    @staticmethod
    def generate_team_hash(team_id, subdomain):
        return str(sha1_hex("{}{}".format(team_id, subdomain)))

    def refresh(self):
        self.rename()

    def rename(self):
        pass

    def is_user_present(self, user_id):
        user = self.users.get(user_id)
        if user and user.presence == 'active':
            return True
        else:
            return False

    def mark_read(self, ts=None, update_remote=True, force=False):
        pass

    def connect(self):
        if not self.connected and not self.connecting_ws:
            if self.ws_url:
                self.connecting_ws = True
                try:
                    # only http proxy is currently supported
                    proxy = ProxyWrapper()
                    if proxy.has_proxy == True:
                        ws = create_connection(self.ws_url, sslopt=sslopt_ca_certs, http_proxy_host=proxy.proxy_address, http_proxy_port=proxy.proxy_port, http_proxy_auth=(proxy.proxy_user, proxy.proxy_password))
                    else:
                        ws = create_connection(self.ws_url, sslopt=sslopt_ca_certs)

                    self.hook = w.hook_fd(ws.sock.fileno(), 1, 0, 0, "receive_ws_callback", self.get_team_hash())
                    ws.sock.setblocking(0)
                    self.ws = ws
                    self.set_reconnect_url(None)
                    self.set_connected()
                    self.connecting_ws = False
                except:
                    w.prnt(self.channel_buffer,
                            'Failed connecting to slack team {}, retrying.'.format(self.domain))
                    dbg('connect failed with exception:\n{}'.format(format_exc_tb()), level=5)
                    self.connecting_ws = False
                    return False
            elif not self.connecting_rtm:
                # The fast reconnect failed, so start over-ish
                for chan in self.channels:
                    self.channels[chan].got_history = False
                s = initiate_connection(self.token, retries=999, team=self)
                self.eventrouter.receive(s)
                self.connecting_rtm = True

    def set_connected(self):
        self.connected = True
        self.last_pong_time = time.time()
        self.buffer_prnt('Connected to Slack team {} ({}) with username {}'.format(
            self.team_info["name"], self.domain, self.nick))
        dbg("connected to {}".format(self.domain))

    def set_disconnected(self):
        w.unhook(self.hook)
        self.connected = False

    def set_reconnect_url(self, url):
        self.ws_url = url

    def next_ws_transaction_id(self):
        self.ws_counter += 1
        return self.ws_counter

    def send_to_websocket(self, data, expect_reply=True):
        data["id"] = self.next_ws_transaction_id()
        message = json.dumps(data)
        try:
            if expect_reply:
                self.ws_replies[data["id"]] = data
            self.ws.send(encode_to_utf8(message))
            dbg("Sent {}...".format(message[:100]))
        except (WebSocketConnectionClosedException, socket.error) as e:
            handle_socket_error(e, self, 'send')

    def update_member_presence(self, user, presence):
        user.presence = presence

        for c in self.channels:
            c = self.channels[c]
            if user.id in c.members:
                c.update_nicklist(user.id)

    def subscribe_users_presence(self):
        # FIXME: There is a limitation in the API to the size of the
        # json we can send.
        # We should try to be smarter to fetch the users whom we want to
        # subscribe to.
        users = list(self.users.keys())[:750]
        if self.myidentifier not in users:
            users.append(self.myidentifier)
        self.send_to_websocket({
            "type": "presence_sub",
            "ids": users,
        }, expect_reply=False)


class SlackChannelCommon(object):
    def send_add_reaction(self, msg_id, reaction):
        self.send_change_reaction("reactions.add", msg_id, reaction)

    def send_remove_reaction(self, msg_id, reaction):
        self.send_change_reaction("reactions.remove", msg_id, reaction)

    def send_change_reaction(self, method, msg_id, reaction):
        if type(msg_id) is not int:
            if msg_id in self.hashed_messages:
                timestamp = str(self.hashed_messages[msg_id])
            else:
                return
        elif 0 < msg_id <= len(self.messages):
            keys = self.main_message_keys_reversed()
            timestamp = next(islice(keys, msg_id - 1, None))
        else:
            return
        data = {"channel": self.identifier, "timestamp": timestamp, "name": reaction}
        s = SlackRequest(self.team, method, data, channel=self, metadata={'reaction': reaction})
        self.eventrouter.receive(s)

    def edit_nth_previous_message(self, msg_id, old, new, flags):
        message = self.my_last_message(msg_id)
        if message is None:
            return
        if new == "" and old == "":
            s = SlackRequest(self.team, "chat.delete", {"channel": self.identifier, "ts": message['ts']}, channel=self)
            self.eventrouter.receive(s)
        else:
            num_replace = 0 if 'g' in flags else 1
            f = re.UNICODE
            f |= re.IGNORECASE if 'i' in flags else 0
            f |= re.MULTILINE if 'm' in flags else 0
            f |= re.DOTALL if 's' in flags else 0
            new_message = re.sub(old, new, message["text"], num_replace, f)
            if new_message != message["text"]:
                s = SlackRequest(self.team, "chat.update",
                        {"channel": self.identifier, "ts": message['ts'], "text": new_message}, channel=self)
                self.eventrouter.receive(s)

    def my_last_message(self, msg_id):
        if type(msg_id) is not int:
            ts = self.hashed_messages.get(msg_id)
            m = self.messages.get(ts)
            if m is not None and m.message_json.get("user") == self.team.myidentifier:
                return m.message_json
        else:
            for key in self.main_message_keys_reversed():
                m = self.messages[key]
                if m.message_json.get("user") == self.team.myidentifier:
                    msg_id -= 1
                    if msg_id == 0:
                        return m.message_json

    def change_message(self, ts, message_json=None, text=None):
        ts = SlackTS(ts)
        m = self.messages.get(ts)
        if not m:
            return
        if message_json:
            m.message_json.update(message_json)
        if text:
            m.change_text(text)

        if type(m) == SlackMessage or config.thread_messages_in_channel:
            new_text = self.render(m, force=True)
            modify_buffer_line(self.channel_buffer, ts, new_text)
        if type(m) == SlackThreadMessage:
            thread_channel = m.parent_message.thread_channel
            if thread_channel and thread_channel.active:
                new_text = thread_channel.render(m, force=True)
                modify_buffer_line(thread_channel.channel_buffer, ts, new_text)

    def hash_message(self, ts):
        ts = SlackTS(ts)

        def calc_hash(ts):
            return sha1_hex(str(ts))

        if ts in self.messages and not self.messages[ts].hash:
            message = self.messages[ts]
            tshash = calc_hash(message.ts)
            hl = 3

            for i in range(hl, len(tshash) + 1):
                shorthash = tshash[:i]
                if self.hashed_messages.get(shorthash) == ts:
                    message.hash = shorthash
                    return shorthash

            shorthash = tshash[:hl]
            while any(x.startswith(shorthash) for x in self.hashed_messages):
                hl += 1
                shorthash = tshash[:hl]

            if shorthash[:-1] in self.hashed_messages:
                col_ts = self.hashed_messages.pop(shorthash[:-1])
                col_new_hash = calc_hash(col_ts)[:hl]
                self.hashed_messages[col_new_hash] = col_ts
                col_msg = self.messages.get(col_ts)
                if col_msg:
                    col_msg.hash = col_new_hash
                    self.change_message(str(col_msg.ts))
                    if col_msg.thread_channel:
                        col_msg.thread_channel.rename()

            self.hashed_messages[shorthash] = message.ts
            message.hash = shorthash
            return shorthash
        elif ts in self.messages:
            return self.messages[ts].hash



class SlackChannel(SlackChannelCommon):
    """
    Represents an individual slack channel.
    """

    def __init__(self, eventrouter, **kwargs):
        # We require these two things for a valid object,
        # the rest we can just learn from slack
        self.active = False
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.eventrouter = eventrouter
        self.slack_name = kwargs["name"]
        self.slack_purpose = kwargs.get("purpose", {"value": ""})
        self.topic = kwargs.get("topic", {"value": ""})
        self.identifier = kwargs["id"]
        self.last_read = SlackTS(kwargs.get("last_read", SlackTS()))
        self.channel_buffer = None
        self.team = kwargs.get('team')
        self.got_history = False
        self.messages = OrderedDict()
        self.hashed_messages = {}
        self.thread_channels = {}
        self.new_messages = False
        self.typing = {}
        self.type = 'channel'
        self.set_name(self.slack_name)
        # short name relates to the localvar we change for typing indication
        self.current_short_name = self.name
        self.set_members(kwargs.get('members', []))
        self.unread_count_display = 0
        self.last_line_from = None

    def __eq__(self, compare_str):
        if compare_str == self.slack_name or compare_str == self.formatted_name() or compare_str == self.formatted_name(style="long_default"):
            return True
        else:
            return False

    def __repr__(self):
        return "Name:{} Identifier:{}".format(self.name, self.identifier)

    @property
    def muted(self):
        return self.identifier in self.team.muted_channels

    def set_name(self, slack_name):
        self.name = "#" + slack_name

    def refresh(self):
        return self.rename()

    def rename(self):
        if self.channel_buffer:
            new_name = self.formatted_name(typing=self.is_someone_typing(), style="sidebar")
            if self.current_short_name != new_name:
                self.current_short_name = new_name
                w.buffer_set(self.channel_buffer, "short_name", new_name)
                return True
        return False

    def set_members(self, members):
        self.members = set(members)
        self.update_nicklist()

    def get_members(self):
        return self.members

    def set_unread_count_display(self, count):
        self.unread_count_display = count
        self.new_messages = bool(self.unread_count_display)
        if self.muted and config.muted_channels_activity != "all":
            return
        for c in range(self.unread_count_display):
            if self.type in ["im", "mpim"]:
                w.buffer_set(self.channel_buffer, "hotlist", "2")
            else:
                w.buffer_set(self.channel_buffer, "hotlist", "1")

    def formatted_name(self, style="default", typing=False, **kwargs):
        if typing and config.channel_name_typing_indicator:
            prepend = ">"
        elif self.type == "group" or self.type == "private":
            prepend = config.group_name_prefix
        elif self.type == "shared":
            prepend = config.shared_name_prefix
        else:
            prepend = "#"
        sidebar_color = config.color_buflist_muted_channels if self.muted else ""
        select = {
            "default": prepend + self.slack_name,
            "sidebar": colorize_string(sidebar_color, prepend + self.slack_name),
            "base": self.slack_name,
            "long_default": "{}.{}{}".format(self.team.preferred_name, prepend, self.slack_name),
            "long_base": "{}.{}".format(self.team.preferred_name, self.slack_name),
        }
        return select[style]

    def render_topic(self, fallback_to_purpose=False):
        topic = self.topic['value']
        if not topic and fallback_to_purpose:
            topic = self.slack_purpose['value']
        return unhtmlescape(unfurl_refs(topic))

    def set_topic(self, value=None):
        if value is not None:
            self.topic = {"value": value}
        if self.channel_buffer:
            topic = self.render_topic(fallback_to_purpose=True)
            w.buffer_set(self.channel_buffer, "title", topic)

    def update_from_message_json(self, message_json):
        for key, value in message_json.items():
            setattr(self, key, value)

    def open(self, update_remote=True):
        if update_remote:
            if "join" in SLACK_API_TRANSLATOR[self.type]:
                s = SlackRequest(self.team, SLACK_API_TRANSLATOR[self.type]["join"],
                        {"channel": self.identifier}, channel=self)
                self.eventrouter.receive(s)
        self.create_buffer()
        self.active = True
        self.get_history()

    def check_should_open(self, force=False):
        if hasattr(self, "is_archived") and self.is_archived:
            return

        if force:
            self.create_buffer()
            return

        # Only check is_member if is_open is not set, because in some cases
        # (e.g. group DMs), is_member should be ignored in favor of is_open.
        is_open = self.is_open if hasattr(self, "is_open") else self.is_member
        if is_open or self.unread_count_display:
            self.create_buffer()
            if config.background_load_all_history:
                self.get_history(slow_queue=True)

    def set_related_server(self, team):
        self.team = team

    def highlights(self):
        nick_highlights = {'@' + self.team.nick, self.team.myidentifier}
        subteam_highlights = {subteam.handle for subteam in self.team.subteams.values()
                if subteam.is_member}
        highlights = nick_highlights | subteam_highlights | self.team.highlight_words
        if self.muted and config.muted_channels_activity == "personal_highlights":
            return highlights
        else:
            return highlights | {"@channel", "@everyone", "@group", "@here"}

    def set_highlights(self):
        # highlight my own name and any set highlights
        if self.channel_buffer:
            h_str = ",".join(self.highlights())
            w.buffer_set(self.channel_buffer, "highlight_words", h_str)

            if self.muted and config.muted_channels_activity != "all":
                notify_level = "0" if config.muted_channels_activity == "none" else "1"
                w.buffer_set(self.channel_buffer, "notify", notify_level)
            else:
                w.buffer_set(self.channel_buffer, "notify", "3")

            if self.muted and config.muted_channels_activity == "none":
                w.buffer_set(self.channel_buffer, "highlight_tags_restrict", "highlight_force")
            else:
                w.buffer_set(self.channel_buffer, "highlight_tags_restrict", "")

            for thread_channel in self.thread_channels.values():
                thread_channel.set_highlights(h_str)

    def create_buffer(self):
        """
        Creates the weechat buffer where the channel magic happens.
        """
        if not self.channel_buffer:
            self.active = True
            self.channel_buffer = w.buffer_new(self.formatted_name(style="long_default"), "buffer_input_callback", "EVENTROUTER", "", "")
            self.eventrouter.weechat_controller.register_buffer(self.channel_buffer, self)
            if self.type == "im":
                w.buffer_set(self.channel_buffer, "localvar_set_type", 'private')
            else:
                w.buffer_set(self.channel_buffer, "localvar_set_type", 'channel')
            w.buffer_set(self.channel_buffer, "localvar_set_channel", self.formatted_name())
            w.buffer_set(self.channel_buffer, "localvar_set_nick", self.team.nick)
            w.buffer_set(self.channel_buffer, "short_name", self.formatted_name(style="sidebar", enable_color=True))
            self.set_highlights()
            self.set_topic()
            self.eventrouter.weechat_controller.set_refresh_buffer_list(True)
            if self.channel_buffer:
                w.buffer_set(self.channel_buffer, "localvar_set_server", self.team.preferred_name)
        self.update_nicklist()

        if "info" in SLACK_API_TRANSLATOR[self.type]:
            s = SlackRequest(self.team, SLACK_API_TRANSLATOR[self.type]["info"],
                    {"channel": self.identifier}, channel=self)
            self.eventrouter.receive(s)

        if self.type == "im":
            if "join" in SLACK_API_TRANSLATOR[self.type]:
                s = SlackRequest(self.team, SLACK_API_TRANSLATOR[self.type]["join"],
                        {"users": self.user, "return_im": True}, channel=self)
                self.eventrouter.receive(s)

    def clear_messages(self):
        w.buffer_clear(self.channel_buffer)
        self.messages = OrderedDict()
        self.got_history = False

    def destroy_buffer(self, update_remote):
        self.clear_messages()
        self.channel_buffer = None
        self.active = False
        if update_remote and not self.eventrouter.shutting_down:
            s = SlackRequest(self.team, SLACK_API_TRANSLATOR[self.type]["leave"],
                    {"channel": self.identifier}, channel=self)
            self.eventrouter.receive(s)

    def buffer_prnt(self, nick, text, timestamp=str(time.time()), tagset=None, tag_nick=None, history_message=False, extra_tags=None):
        data = "{}\t{}".format(format_nick(nick, self.last_line_from), text)
        self.last_line_from = nick
        ts = SlackTS(timestamp)
        last_read = SlackTS(self.last_read)
        # without this, DMs won't open automatically
        if not self.channel_buffer and ts > last_read:
            self.open(update_remote=False)
        if self.channel_buffer:
            # backlog messages - we will update the read marker as we print these
            backlog = ts <= last_read
            if not backlog:
                self.new_messages = True

            if not tagset:
                if self.type in ["im", "mpim"]:
                    tagset = "dm"
                else:
                    tagset = "channel"

            no_log = history_message and backlog
            self_msg = tag_nick == self.team.nick
            tags = tag(tagset, user=tag_nick, self_msg=self_msg, backlog=backlog, no_log=no_log, extra_tags=extra_tags)

            try:
                if (config.unhide_buffers_with_activity
                        and not self.is_visible() and not self.muted):
                    w.buffer_set(self.channel_buffer, "hidden", "0")

                w.prnt_date_tags(self.channel_buffer, ts.major, tags, data)
                modify_last_print_time(self.channel_buffer, ts.minor)
                if backlog or self_msg:
                    self.mark_read(ts, update_remote=False, force=True)
            except:
                dbg("Problem processing buffer_prnt")

    def send_message(self, message, subtype=None, request_dict_ext={}):
        message = linkify_text(message, self.team)
        dbg(message)
        if subtype == 'me_message':
            s = SlackRequest(self.team, "chat.meMessage", {"channel": self.identifier, "text": message}, channel=self)
            self.eventrouter.receive(s)
        else:
            request = {"type": "message", "channel": self.identifier,
                    "text": message, "user": self.team.myidentifier}
            request.update(request_dict_ext)
            self.team.send_to_websocket(request)

    def store_message(self, message, team, from_me=False):
        if not self.active:
            return
        if from_me:
            message.message_json["user"] = team.myidentifier
        self.messages[SlackTS(message.ts)] = message

        sorted_messages = sorted(self.messages.items())
        messages_to_delete = sorted_messages[:-SCROLLBACK_SIZE]
        messages_to_keep = sorted_messages[-SCROLLBACK_SIZE:]
        for message_hash in [m[1].hash for m in messages_to_delete]:
            if message_hash in self.hashed_messages:
                del self.hashed_messages[message_hash]
        self.messages = OrderedDict(messages_to_keep)

    def is_visible(self):
        return w.buffer_get_integer(self.channel_buffer, "hidden") == 0

    def get_history(self, slow_queue=False):
        if not self.got_history:
            # we have probably reconnected. flush the buffer
            if self.team.connected:
                self.clear_messages()
            w.prnt_date_tags(self.channel_buffer, SlackTS().major,
                    tag(backlog=True, no_log=True), '\tgetting channel history...')
            s = SlackRequest(self.team, SLACK_API_TRANSLATOR[self.type]["history"],
                    {"channel": self.identifier, "count": BACKLOG_SIZE}, channel=self, metadata={'clear': True})
            if not slow_queue:
                self.eventrouter.receive(s)
            else:
                self.eventrouter.receive_slow(s)
            self.got_history = True

    def main_message_keys_reversed(self):
        return (key for key in reversed(self.messages)
                if type(self.messages[key]) == SlackMessage)

    # Typing related
    def set_typing(self, user):
        if self.channel_buffer and self.is_visible():
            self.typing[user] = time.time()
            self.eventrouter.weechat_controller.set_refresh_buffer_list(True)

    def unset_typing(self, user):
        if self.channel_buffer and self.is_visible():
            u = self.typing.get(user)
            if u:
                self.eventrouter.weechat_controller.set_refresh_buffer_list(True)

    def is_someone_typing(self):
        """
        Walks through dict of typing folks in a channel and fast
        returns if any of them is actively typing. If none are,
        nulls the dict and returns false.
        """
        for user, timestamp in self.typing.items():
            if timestamp + 4 > time.time():
                return True
        if len(self.typing) > 0:
            self.typing = {}
            self.eventrouter.weechat_controller.set_refresh_buffer_list(True)
        return False

    def get_typing_list(self):
        """
        Returns the names of everyone in the channel who is currently typing.
        """
        typing = []
        for user, timestamp in self.typing.items():
            if timestamp + 4 > time.time():
                typing.append(user)
            else:
                del self.typing[user]
        return typing

    def mark_read(self, ts=None, update_remote=True, force=False):
        if self.new_messages or force:
            if self.channel_buffer:
                w.buffer_set(self.channel_buffer, "unread", "")
                w.buffer_set(self.channel_buffer, "hotlist", "-1")
            if not ts:
                ts = next(reversed(self.messages), SlackTS())
            if ts > self.last_read:
                self.last_read = ts
            if update_remote:
                s = SlackRequest(self.team, SLACK_API_TRANSLATOR[self.type]["mark"],
                        {"channel": self.identifier, "ts": ts}, channel=self)
                self.eventrouter.receive(s)
                self.new_messages = False

    def user_joined(self, user_id):
        # ugly hack - for some reason this gets turned into a list
        self.members = set(self.members)
        self.members.add(user_id)
        self.update_nicklist(user_id)

    def user_left(self, user_id):
        self.members.discard(user_id)
        self.update_nicklist(user_id)

    def update_nicklist(self, user=None):
        if not self.channel_buffer:
            return
        if self.type not in ["channel", "group", "mpim", "private", "shared"]:
            return
        w.buffer_set(self.channel_buffer, "nicklist", "1")
        # create nicklists for the current channel if they don't exist
        # if they do, use the existing pointer
        here = w.nicklist_search_group(self.channel_buffer, '', NICK_GROUP_HERE)
        if not here:
            here = w.nicklist_add_group(self.channel_buffer, '', NICK_GROUP_HERE, "weechat.color.nicklist_group", 1)
        afk = w.nicklist_search_group(self.channel_buffer, '', NICK_GROUP_AWAY)
        if not afk:
            afk = w.nicklist_add_group(self.channel_buffer, '', NICK_GROUP_AWAY, "weechat.color.nicklist_group", 1)

        # Add External nicklist group only for shared channels
        if self.type == 'shared':
            external = w.nicklist_search_group(self.channel_buffer, '', NICK_GROUP_EXTERNAL)
            if not external:
                external = w.nicklist_add_group(self.channel_buffer, '', NICK_GROUP_EXTERNAL, 'weechat.color.nicklist_group', 2)

        if user and len(self.members) < 1000:
            user = self.team.users.get(user)
            # External users that have left shared channels won't exist
            if not user or user.deleted:
                return
            nick = w.nicklist_search_nick(self.channel_buffer, "", user.name)
            # since this is a change just remove it regardless of where it is
            w.nicklist_remove_nick(self.channel_buffer, nick)
            # now add it back in to whichever..
            nick_group = afk
            if user.is_external:
                nick_group = external
            elif self.team.is_user_present(user.identifier):
                nick_group = here
            if user.identifier in self.members:
                w.nicklist_add_nick(self.channel_buffer, nick_group, user.name, user.color_name, "", "", 1)

        # if we didn't get a user, build a complete list. this is expensive.
        else:
            if len(self.members) < 1000:
                try:
                    for user in self.members:
                        user = self.team.users.get(user)
                        if user.deleted:
                            continue
                        nick_group = afk
                        if user.is_external:
                            nick_group = external
                        elif self.team.is_user_present(user.identifier):
                            nick_group = here
                        w.nicklist_add_nick(self.channel_buffer, nick_group, user.name, user.color_name, "", "", 1)
                except:
                    dbg("DEBUG: {} {} {}".format(self.identifier, self.name, format_exc_only()))
            else:
                w.nicklist_remove_all(self.channel_buffer)
                for fn in ["1| too", "2| many", "3| users", "4| to", "5| show"]:
                    w.nicklist_add_group(self.channel_buffer, '', fn, w.color('white'), 1)

    def render(self, message, force=False):
        text = message.render(force)
        if isinstance(message, SlackThreadMessage):
            thread_id = message.parent_message.hash or message.parent_message.ts
            return colorize_string(get_thread_color(thread_id), '[{}]'.format(thread_id)) + ' {}'.format(text)

        return text


class SlackDMChannel(SlackChannel):
    """
    Subclass of a normal channel for person-to-person communication, which
    has some important differences.
    """

    def __init__(self, eventrouter, users, **kwargs):
        dmuser = kwargs["user"]
        kwargs["name"] = users[dmuser].name if dmuser in users else dmuser
        super(SlackDMChannel, self).__init__(eventrouter, **kwargs)
        self.type = 'im'
        self.update_color()
        self.set_name(self.slack_name)
        if dmuser in users:
            self.set_topic(create_user_status_string(users[dmuser].profile))

    def set_related_server(self, team):
        super(SlackDMChannel, self).set_related_server(team)
        if self.user not in self.team.users:
            s = SlackRequest(self.team, 'users.info', {'user': self.slack_name}, channel=self)
            self.eventrouter.receive(s)

    def set_name(self, slack_name):
        self.name = slack_name

    def get_members(self):
        return {self.user}

    def create_buffer(self):
        if not self.channel_buffer:
            super(SlackDMChannel, self).create_buffer()
            w.buffer_set(self.channel_buffer, "localvar_set_type", 'private')

    def update_color(self):
        if config.colorize_private_chats:
            self.color_name = get_nick_color(self.name)
        else:
            self.color_name = ""

    def formatted_name(self, style="default", typing=False, present=True, enable_color=False, **kwargs):
        prepend = ""
        if config.show_buflist_presence:
            prepend = "+" if present else " "
        select = {
            "default": self.slack_name,
            "sidebar": prepend + self.slack_name,
            "base": self.slack_name,
            "long_default": "{}.{}".format(self.team.preferred_name, self.slack_name),
            "long_base": "{}.{}".format(self.team.preferred_name, self.slack_name),
        }
        if config.colorize_private_chats and enable_color:
            return colorize_string(self.color_name, select[style])
        else:
            return select[style]

    def open(self, update_remote=True):
        self.create_buffer()
        self.get_history()
        if "info" in SLACK_API_TRANSLATOR[self.type]:
            s = SlackRequest(self.team, SLACK_API_TRANSLATOR[self.type]["info"],
                    {"name": self.identifier}, channel=self)
            self.eventrouter.receive(s)
        if update_remote:
            if "join" in SLACK_API_TRANSLATOR[self.type]:
                s = SlackRequest(self.team, SLACK_API_TRANSLATOR[self.type]["join"],
                        {"users": self.user, "return_im": True}, channel=self)
                self.eventrouter.receive(s)

    def rename(self):
        if self.channel_buffer:
            new_name = self.formatted_name(style="sidebar", present=self.team.is_user_present(self.user), enable_color=config.colorize_private_chats)
            if self.current_short_name != new_name:
                self.current_short_name = new_name
                w.buffer_set(self.channel_buffer, "short_name", new_name)
                return True
        return False

    def refresh(self):
        return self.rename()


class SlackGroupChannel(SlackChannel):
    """
    A group channel is a private discussion group.
    """

    def __init__(self, eventrouter, **kwargs):
        super(SlackGroupChannel, self).__init__(eventrouter, **kwargs)
        self.type = "group"
        self.set_name(self.slack_name)

    def set_name(self, slack_name):
        self.name = config.group_name_prefix + slack_name


class SlackPrivateChannel(SlackGroupChannel):
    """
    A private channel is a private discussion group. At the time of writing, it
    differs from group channels in that group channels are channels initially
    created as private, while private channels are public channels which are
    later converted to private.
    """

    def __init__(self, eventrouter, **kwargs):
        super(SlackPrivateChannel, self).__init__(eventrouter, **kwargs)
        self.type = "private"

    def set_related_server(self, team):
        super(SlackPrivateChannel, self).set_related_server(team)
        # Fetch members here (after the team is known) since they aren't
        # included in rtm.start
        s = SlackRequest(team, 'conversations.members', {'channel': self.identifier}, channel=self)
        self.eventrouter.receive(s)


class SlackMPDMChannel(SlackChannel):
    """
    An MPDM channel is a special instance of a 'group' channel.
    We change the name to look less terrible in weechat.
    """

    def __init__(self, eventrouter, team_users, myidentifier, **kwargs):
        kwargs["name"] = ','.join(sorted(
                getattr(team_users.get(user_id), 'name', user_id)
                for user_id in kwargs["members"]
                if user_id != myidentifier
        ))
        super(SlackMPDMChannel, self).__init__(eventrouter, **kwargs)
        self.type = "mpim"

    def open(self, update_remote=True):
        self.create_buffer()
        self.active = True
        self.get_history()
        if "info" in SLACK_API_TRANSLATOR[self.type]:
            s = SlackRequest(self.team, SLACK_API_TRANSLATOR[self.type]["info"],
                    {"channel": self.identifier}, channel=self)
            self.eventrouter.receive(s)
        if update_remote and 'join' in SLACK_API_TRANSLATOR[self.type]:
            s = SlackRequest(self.team, SLACK_API_TRANSLATOR[self.type]['join'],
                    {'users': ','.join(self.members)}, channel=self)
            self.eventrouter.receive(s)

    def set_name(self, slack_name):
        self.name = slack_name

    def formatted_name(self, style="default", typing=False, **kwargs):
        if typing and config.channel_name_typing_indicator:
            prepend = ">"
        else:
            prepend = "@"
        select = {
            "default": self.name,
            "sidebar": prepend + self.name,
            "base": self.name,
            "long_default": "{}.{}".format(self.team.preferred_name, self.name),
            "long_base": "{}.{}".format(self.team.preferred_name, self.name),
        }
        return select[style]

    def rename(self):
        pass


class SlackSharedChannel(SlackChannel):
    def __init__(self, eventrouter, **kwargs):
        super(SlackSharedChannel, self).__init__(eventrouter, **kwargs)
        self.type = 'shared'

    def set_related_server(self, team):
        super(SlackSharedChannel, self).set_related_server(team)
        # Fetch members here (after the team is known) since they aren't
        # included in rtm.start
        s = SlackRequest(team, 'conversations.members', {'channel': self.identifier}, channel=self)
        self.eventrouter.receive(s)

    def get_history(self, slow_queue=False):
        # Get info for external users in the channel
        for user in self.members - set(self.team.users.keys()):
            s = SlackRequest(self.team, 'users.info', {'user': user}, channel=self)
            self.eventrouter.receive(s)
        super(SlackSharedChannel, self).get_history(slow_queue)

    def set_name(self, slack_name):
        self.name = config.shared_name_prefix + slack_name


class SlackThreadChannel(SlackChannelCommon):
    """
    A thread channel is a virtual channel. We don't inherit from
    SlackChannel, because most of how it operates will be different.
    """

    def __init__(self, eventrouter, parent_message):
        self.eventrouter = eventrouter
        self.parent_message = parent_message
        self.hashed_messages = {}
        self.channel_buffer = None
        self.type = "thread"
        self.got_history = False
        self.label = None
        self.members = self.parent_message.channel.members
        self.team = self.parent_message.team
        self.last_line_from = None

    @property
    def identifier(self):
        return self.parent_message.channel.identifier

    @property
    def messages(self):
        return self.parent_message.channel.messages

    @property
    def muted(self):
        return self.parent_message.channel.muted

    def formatted_name(self, style="default", **kwargs):
        hash_or_ts = self.parent_message.hash or self.parent_message.ts
        styles = {
            "default": " +{}".format(hash_or_ts),
            "long_default": "{}.{}".format(self.parent_message.channel.formatted_name(style="long_default"), hash_or_ts),
            "sidebar": " +{}".format(hash_or_ts),
        }
        return styles[style]

    def refresh(self):
        self.rename()

    def mark_read(self, ts=None, update_remote=True, force=False):
        if self.channel_buffer:
            w.buffer_set(self.channel_buffer, "unread", "")
            w.buffer_set(self.channel_buffer, "hotlist", "-1")

    def buffer_prnt(self, nick, text, timestamp, tag_nick=None):
        data = "{}\t{}".format(format_nick(nick, self.last_line_from), text)
        self.last_line_from = nick
        ts = SlackTS(timestamp)
        if self.channel_buffer:
            if self.parent_message.channel.type in ["im", "mpim"]:
                tagset = "dm"
            else:
                tagset = "channel"
            self_msg = tag_nick == self.team.nick
            tags = tag(tagset, user=tag_nick, self_msg=self_msg)

            w.prnt_date_tags(self.channel_buffer, ts.major, tags, data)
            modify_last_print_time(self.channel_buffer, ts.minor)
            if self_msg:
                self.mark_read(ts, update_remote=False, force=True)

    def get_history(self):
        self.got_history = True
        for message in chain([self.parent_message], self.parent_message.submessages):
            text = self.render(message)
            self.buffer_prnt(message.sender, text, message.ts, tag_nick=message.sender_plain)
        if len(self.parent_message.submessages) < self.parent_message.number_of_replies():
            s = SlackRequest(self.team, "conversations.replies",
                    {"channel": self.identifier, "ts": self.parent_message.ts},
                    channel=self.parent_message.channel)
            self.eventrouter.receive(s)

    def main_message_keys_reversed(self):
        return (message.ts for message in reversed(self.parent_message.submessages))

    def send_message(self, message, subtype=None, request_dict_ext={}):
        if subtype == 'me_message':
            w.prnt("", "ERROR: /me is not supported in threads")
            return w.WEECHAT_RC_ERROR
        message = linkify_text(message, self.team)
        dbg(message)
        request = {"type": "message", "text": message,
                "channel": self.parent_message.channel.identifier,
                "thread_ts": str(self.parent_message.ts),
                "user": self.team.myidentifier}
        request.update(request_dict_ext)
        self.team.send_to_websocket(request)

    def open(self, update_remote=True):
        self.create_buffer()
        self.active = True
        self.get_history()

    def rename(self):
        if self.channel_buffer and not self.label:
            w.buffer_set(self.channel_buffer, "short_name", self.formatted_name(style="sidebar", enable_color=True))

    def set_highlights(self, highlight_string=None):
        if self.channel_buffer:
            if highlight_string is None:
                highlight_string = ",".join(self.parent_message.channel.highlights())
            w.buffer_set(self.channel_buffer, "highlight_words", highlight_string)

    def create_buffer(self):
        """
        Creates the weechat buffer where the thread magic happens.
        """
        if not self.channel_buffer:
            self.channel_buffer = w.buffer_new(self.formatted_name(style="long_default"), "buffer_input_callback", "EVENTROUTER", "", "")
            self.eventrouter.weechat_controller.register_buffer(self.channel_buffer, self)
            w.buffer_set(self.channel_buffer, "localvar_set_type", 'channel')
            w.buffer_set(self.channel_buffer, "localvar_set_nick", self.team.nick)
            w.buffer_set(self.channel_buffer, "localvar_set_channel", self.formatted_name())
            w.buffer_set(self.channel_buffer, "localvar_set_server", self.team.preferred_name)
            w.buffer_set(self.channel_buffer, "short_name", self.formatted_name(style="sidebar", enable_color=True))
            self.set_highlights()
            time_format = w.config_string(w.config_get("weechat.look.buffer_time_format"))
            parent_time = time.localtime(SlackTS(self.parent_message.ts).major)
            topic = '{} {} | {}'.format(time.strftime(time_format, parent_time), self.parent_message.sender, self.render(self.parent_message)	)
            w.buffer_set(self.channel_buffer, "title", topic)

            # self.eventrouter.weechat_controller.set_refresh_buffer_list(True)

    def destroy_buffer(self, update_remote):
        self.channel_buffer = None
        self.got_history = False
        self.active = False

    def render(self, message, force=False):
        return message.render(force)


class SlackUser(object):
    """
    Represends an individual slack user. Also where you set their name formatting.
    """

    def __init__(self, originating_team_id, **kwargs):
        self.identifier = kwargs["id"]
        # These attributes may be missing in the response, so we have to make
        # sure they're set
        self.profile = {}
        self.presence = kwargs.get("presence", "unknown")
        self.deleted = kwargs.get("deleted", False)
        self.is_external = (not kwargs.get("is_bot") and
                kwargs.get("team_id") != originating_team_id)
        for key, value in kwargs.items():
            setattr(self, key, value)

        self.name = nick_from_profile(self.profile, kwargs["name"])
        self.username = kwargs["name"]
        self.update_color()

    def __repr__(self):
        return "Name:{} Identifier:{}".format(self.name, self.identifier)

    def force_color(self, color_name):
        self.color_name = color_name

    def update_color(self):
        # This will automatically be none/"" if the user has disabled nick
        # colourization.
        self.color_name = get_nick_color(self.name)

    def update_status(self, status_emoji, status_text):
        self.profile["status_emoji"] = status_emoji
        self.profile["status_text"] = status_text

    def formatted_name(self, prepend="", enable_color=True):
        name = prepend + self.name
        if enable_color:
            return colorize_string(self.color_name, name)
        else:
            return name


class SlackBot(SlackUser):
    """
    Basically the same as a user, but split out to identify and for future
    needs
    """
    def __init__(self, originating_team_id, **kwargs):
        super(SlackBot, self).__init__(originating_team_id, is_bot=True, **kwargs)


class SlackMessage(object):
    """
    Represents a single slack message and associated context/metadata.
    These are modifiable and can be rerendered to change a message,
    delete a message, add a reaction, add a thread.
    Note: these can't be tied to a SlackUser object because users
    can be deleted, so we have to store sender in each one.
    """
    def __init__(self, message_json, team, channel, override_sender=None):
        self.team = team
        self.channel = channel
        self.message_json = message_json
        self.submessages = []
        self.hash = None
        if override_sender:
            self.sender = override_sender
            self.sender_plain = override_sender
        else:
            senders = self.get_sender()
            self.sender, self.sender_plain = senders[0], senders[1]
        self.ts = SlackTS(message_json['ts'])

    def __hash__(self):
        return hash(self.ts)

    @property
    def thread_channel(self):
        return self.channel.thread_channels.get(self.ts)

    def open_thread(self, switch=False):
        if not self.thread_channel or not self.thread_channel.active:
            self.channel.thread_channels[self.ts] = SlackThreadChannel(EVENTROUTER, self)
            self.thread_channel.open()
        if switch:
            w.buffer_set(self.thread_channel.channel_buffer, "display", "1")

    def render(self, force=False):
        # If we already have a rendered version in the object, just return that.
        if not force and self.message_json.get("_rendered_text"):
            return self.message_json["_rendered_text"]

        if "fallback" in self.message_json:
            text = self.message_json["fallback"]
        elif self.message_json.get("text"):
            text = self.message_json["text"]
        else:
            text = ""

        if self.message_json.get('mrkdwn', True):
            text = render_formatting(text)

        if (self.message_json.get('subtype') in ('channel_join', 'group_join') and
                self.message_json.get('inviter')):
            inviter_id = self.message_json.get('inviter')
            text += " by invitation from <@{}>".format(inviter_id)

        if "blocks" in self.message_json:
            text += unfurl_blocks(self.message_json)

        text = unfurl_refs(text)

        if (self.message_json.get('subtype') == 'me_message' and
                not self.message_json['text'].startswith(self.sender)):
            text = "{} {}".format(self.sender, text)

        if "edited" in self.message_json:
            text += " " + colorize_string(config.color_edited_suffix, '(edited)')

        text += unfurl_refs(unwrap_attachments(self.message_json, text))
        text += unfurl_refs(unwrap_files(self.message_json, text))
        text = unhtmlescape(text.lstrip().replace("\t", "    "))

        text += create_reactions_string(
                self.message_json.get("reactions", ""), self.team.myidentifier)

        if self.number_of_replies():
            self.channel.hash_message(self.ts)
            text += " " + colorize_string(get_thread_color(self.hash), "[ Thread: {} Replies: {} ]".format(
                    self.hash, self.number_of_replies()))

        text = replace_string_with_emoji(text)

        self.message_json["_rendered_text"] = text
        return text

    def change_text(self, new_text):
        self.message_json["text"] = new_text
        dbg(self.message_json)

    def get_sender(self):
        name = ""
        name_plain = ""
        user = self.team.users.get(self.message_json.get('user'))
        if user:
            name = "{}".format(user.formatted_name())
            name_plain = "{}".format(user.formatted_name(enable_color=False))
            if user.is_external:
                name += config.external_user_suffix
                name_plain += config.external_user_suffix
        elif 'username' in self.message_json:
            username = self.message_json["username"]
            if self.message_json.get("subtype") == "bot_message":
                name = "{} :]".format(username)
                name_plain = "{}".format(username)
            else:
                name = "-{}-".format(username)
                name_plain = "{}".format(username)
        elif 'service_name' in self.message_json:
            name = "-{}-".format(self.message_json["service_name"])
            name_plain = "{}".format(self.message_json["service_name"])
        elif self.message_json.get('bot_id') in self.team.bots:
            name = "{} :]".format(self.team.bots[self.message_json["bot_id"]].formatted_name())
            name_plain = "{}".format(self.team.bots[self.message_json["bot_id"]].formatted_name(enable_color=False))
        return (name, name_plain)

    def add_reaction(self, reaction, user):
        m = self.message_json.get('reactions')
        if m:
            found = False
            for r in m:
                if r["name"] == reaction and user not in r["users"]:
                    r["users"].append(user)
                    found = True
            if not found:
                self.message_json["reactions"].append({"name": reaction, "users": [user]})
        else:
            self.message_json["reactions"] = [{"name": reaction, "users": [user]}]

    def remove_reaction(self, reaction, user):
        m = self.message_json.get('reactions')
        if m:
            for r in m:
                if r["name"] == reaction and user in r["users"]:
                    r["users"].remove(user)

    def has_mention(self):
        return w.string_has_highlight(unfurl_refs(self.message_json.get('text')),
                ",".join(self.channel.highlights()))

    def number_of_replies(self):
        return max(len(self.submessages), len(self.message_json.get("replies", [])))

    def notify_thread(self, action=None, sender_id=None):
        if config.auto_open_threads:
            self.open_thread()
        elif sender_id != self.team.myidentifier:
            if action == "mention":
                template = "You were mentioned in thread {hash}, channel {channel}"
            elif action == "participant":
                template = "New message in thread {hash}, channel {channel} in which you participated"
            elif action == "response":
                template = "New message in thread {hash} in response to own message in {channel}"
            else:
                template = "Notification for message in thread {hash}, channel {channel}"
            message = template.format(hash=self.hash, channel=self.channel.formatted_name())

            self.team.buffer_prnt(message, message=True)

class SlackThreadMessage(SlackMessage):

    def __init__(self, parent_message, *args):
        super(SlackThreadMessage, self).__init__(*args)
        self.parent_message = parent_message


class Hdata(object):
    def __init__(self, w):
        self.buffer = w.hdata_get('buffer')
        self.line = w.hdata_get('line')
        self.line_data = w.hdata_get('line_data')
        self.lines = w.hdata_get('lines')


class SlackTS(object):

    def __init__(self, ts=None):
        if ts:
            self.major, self.minor = [int(x) for x in ts.split('.', 1)]
        else:
            self.major = int(time.time())
            self.minor = 0

    def __cmp__(self, other):
        if isinstance(other, SlackTS):
            if self.major < other.major:
                return -1
            elif self.major > other.major:
                return 1
            elif self.major == other.major:
                if self.minor < other.minor:
                    return -1
                elif self.minor > other.minor:
                    return 1
                else:
                    return 0
        elif isinstance(other, str):
            s = self.__str__()
            if s < other:
                return -1
            elif s > other:
                return 1
            elif s == other:
                return 0

    def __lt__(self, other):
        return self.__cmp__(other) < 0

    def __le__(self, other):
        return self.__cmp__(other) <= 0

    def __eq__(self, other):
        return self.__cmp__(other) == 0

    def __ge__(self, other):
        return self.__cmp__(other) >= 0

    def __gt__(self, other):
        return self.__cmp__(other) > 0

    def __hash__(self):
        return hash("{}.{}".format(self.major, self.minor))

    def __repr__(self):
        return str("{0}.{1:06d}".format(self.major, self.minor))

    def split(self, *args, **kwargs):
        return [self.major, self.minor]

    def majorstr(self):
        return str(self.major)

    def minorstr(self):
        return str(self.minor)

###### New handlers


def handle_rtmstart(login_data, eventrouter, team, channel, metadata):
    """
    This handles the main entry call to slack, rtm.start
    """
    metadata = login_data["wee_slack_request_metadata"]

    if not login_data["ok"]:
        w.prnt("", "ERROR: Failed connecting to Slack with token {}: {}"
               .format(token_for_print(metadata.token), login_data["error"]))
        if not re.match(r"^xo\w\w(-\d+){3}-[0-9a-f]+$", metadata.token):
            w.prnt("", "ERROR: Token does not look like a valid Slack token. "
                   "Ensure it is a valid token and not just a OAuth code.")

        return

    self_profile = next(
        user["profile"]
        for user in login_data["users"]
        if user["id"] == login_data["self"]["id"]
    )
    self_nick = nick_from_profile(self_profile, login_data["self"]["name"])

    # Let's reuse a team if we have it already.
    th = SlackTeam.generate_team_hash(login_data['team']['id'], login_data['team']['domain'])
    if not eventrouter.teams.get(th):

        users = {}
        for item in login_data["users"]:
            users[item["id"]] = SlackUser(login_data['team']['id'], **item)

        bots = {}
        for item in login_data["bots"]:
            bots[item["id"]] = SlackBot(login_data['team']['id'], **item)

        subteams = {}
        for item in login_data["subteams"]["all"]:
            is_member = item['id'] in login_data["subteams"]["self"]
            subteams[item['id']] = SlackSubteam(
                    login_data['team']['id'], is_member=is_member, **item)

        channels = {}
        for item in login_data["channels"]:
            if item["is_shared"]:
                channels[item["id"]] = SlackSharedChannel(eventrouter, **item)
            elif item["is_private"]:
                channels[item["id"]] = SlackPrivateChannel(eventrouter, **item)
            else:
                channels[item["id"]] = SlackChannel(eventrouter, **item)

        for item in login_data["ims"]:
            channels[item["id"]] = SlackDMChannel(eventrouter, users, **item)

        for item in login_data["groups"]:
            if item["is_mpim"]:
                channels[item["id"]] = SlackMPDMChannel(eventrouter, users, login_data["self"]["id"], **item)
            else:
                channels[item["id"]] = SlackGroupChannel(eventrouter, **item)

        t = SlackTeam(
            eventrouter,
            metadata.token,
            th,
            login_data['url'],
            login_data["team"],
            subteams,
            self_nick,
            login_data["self"]["id"],
            login_data["self"]["manual_presence"],
            users,
            bots,
            channels,
            muted_channels=login_data["self"]["prefs"]["muted_channels"],
            highlight_words=login_data["self"]["prefs"]["highlight_words"],
        )
        eventrouter.register_team(t)

    else:
        t = eventrouter.teams.get(th)
        if t.myidentifier != login_data["self"]["id"]:
            print_error(
                'The Slack team {} has tokens for two different users, this is not supported. The '
                'token {} is for user {}, and the token {} is for user {}. Please remove one of '
                'them.'.format(t.team_info["name"], token_for_print(t.token), t.nick,
                    token_for_print(metadata.token), self_nick)
            )
            return
        elif metadata.metadata.get('initial_connection'):
            print_error(
                'Ignoring duplicate Slack tokens for the same team ({}) and user ({}). The two '
                'tokens are {} and {}.'.format(t.team_info["name"], t.nick,
                    token_for_print(t.token), token_for_print(metadata.token)),
                warning=True
            )
            return
        else:
            t.set_reconnect_url(login_data['url'])
            t.connecting_rtm = False

    t.connect()

def handle_rtmconnect(login_data, eventrouter, team, channel, metadata):
    metadata = login_data["wee_slack_request_metadata"]
    team = metadata.team
    team.connecting_rtm = False

    if not login_data["ok"]:
        w.prnt("", "ERROR: Failed reconnecting to Slack with token {}: {}"
               .format(token_for_print(metadata.token), login_data["error"]))
        return

    team.set_reconnect_url(login_data['url'])
    team.connect()


def handle_emojilist(emoji_json, eventrouter, team, channel, metadata):
    if emoji_json["ok"]:
        team.emoji_completions.extend(emoji_json["emoji"].keys())


def handle_channelsinfo(channel_json, eventrouter, team, channel, metadata):
    channel.set_unread_count_display(channel_json['channel'].get('unread_count_display', 0))
    channel.set_members(channel_json['channel']['members'])


def handle_groupsinfo(group_json, eventrouter, team, channel, metadatas):
    channel.set_unread_count_display(group_json['group'].get('unread_count_display', 0))


def handle_conversationsopen(conversation_json, eventrouter, team, channel, metadata, object_name='channel'):
    # Set unread count if the channel isn't new
    if channel:
        unread_count_display = conversation_json[object_name].get('unread_count_display', 0)
        channel.set_unread_count_display(unread_count_display)


def handle_mpimopen(mpim_json, eventrouter, team, channel, metadata, object_name='group'):
    handle_conversationsopen(mpim_json, eventrouter, team, channel, metadata, object_name)


def handle_history(message_json, eventrouter, team, channel, metadata):
    if metadata['clear']:
        channel.clear_messages()
    channel.got_history = True
    for message in reversed(message_json["messages"]):
        process_message(message, eventrouter, team, channel, metadata, history_message=True)


handle_channelshistory = handle_history
handle_conversationshistory = handle_history
handle_groupshistory = handle_history
handle_imhistory = handle_history
handle_mpimhistory = handle_history


def handle_conversationsreplies(message_json, eventrouter, team, channel, metadata):
    for message in message_json['messages']:
        process_message(message, eventrouter, team, channel, metadata)


def handle_conversationsmembers(members_json, eventrouter, team, channel, metadata):
    if members_json['ok']:
        channel.set_members(members_json['members'])
    else:
        w.prnt(team.channel_buffer, '{}Couldn\'t load members for channel {}. Error: {}'
                .format(w.prefix('error'), channel.name, members_json['error']))


def handle_usersinfo(user_json, eventrouter, team, channel, metadata):
    user_info = user_json['user']
    if not metadata.get('user'):
        user = SlackUser(team.identifier, **user_info)
        team.users[user_info['id']] = user

    if channel.type == 'shared':
        channel.update_nicklist(user_info['id'])
    elif channel.type == 'im':
        channel.slack_name = user.name
        channel.set_topic(create_user_status_string(user.profile))


def handle_usergroupsuserslist(users_json, eventrouter, team, channel, metadata):
    header = 'Users in {}'.format(metadata['usergroup_handle'])
    users = [team.users[key] for key in users_json['users']]
    return print_users_info(team, header, users)


def handle_usersprofileset(json, eventrouter, team, channel, metadata):
    if not json['ok']:
        w.prnt('', 'ERROR: Failed to set profile: {}'.format(json['error']))


def handle_conversationsinvite(json, eventrouter, team, channel, metadata):
    nicks = ', '.join(metadata['nicks'])
    if json['ok']:
        w.prnt(team.channel_buffer, 'Invited {} to {}'.format(nicks, channel.name))
    else:
        w.prnt(team.channel_buffer, 'ERROR: Couldn\'t invite {} to {}. Error: {}'
                .format(nicks, channel.name, json['error']))


def handle_chatcommand(json, eventrouter, team, channel, metadata):
    command = '{} {}'.format(metadata['command'], metadata['command_args']).rstrip()
    response = unfurl_refs(json['response']) if 'response' in json else ''
    if json['ok']:
        response_text = 'Response: {}'.format(response) if response else 'No response'
        w.prnt(team.channel_buffer, 'Ran command "{}". {}' .format(command, response_text))
    else:
        response_text = '. Response: {}'.format(response) if response else ''
        w.prnt(team.channel_buffer, 'ERROR: Couldn\'t run command "{}". Error: {}{}'
                .format(command, json['error'], response_text))


def handle_reactionsadd(json, eventrouter, team, channel, metadata):
    if not json['ok']:
        print_error("Couldn't add reaction {}: {}".format(metadata['reaction'], json['error']))


def handle_reactionsremove(json, eventrouter, team, channel, metadata):
    if not json['ok']:
        print_error("Couldn't remove reaction {}: {}".format(metadata['reaction'], json['error']))


###### New/converted process_ and subprocess_ methods
def process_hello(message_json, eventrouter, team, channel, metadata):
    team.subscribe_users_presence()


def process_reconnect_url(message_json, eventrouter, team, channel, metadata):
    team.set_reconnect_url(message_json['url'])


def process_presence_change(message_json, eventrouter, team, channel, metadata):
    users = [team.users[user_id] for user_id in message_json.get("users", [])]
    if "user" in metadata:
        users.append(metadata["user"])
    for user in users:
        team.update_member_presence(user, message_json["presence"])
    if team.myidentifier in users:
        w.bar_item_update("away")
        w.bar_item_update("slack_away")


def process_manual_presence_change(message_json, eventrouter, team, channel, metadata):
    team.my_manual_presence = message_json["presence"]
    w.bar_item_update("away")
    w.bar_item_update("slack_away")


def process_pref_change(message_json, eventrouter, team, channel, metadata):
    if message_json['name'] == 'muted_channels':
        team.set_muted_channels(message_json['value'])
    elif message_json['name'] == 'highlight_words':
        team.set_highlight_words(message_json['value'])
    else:
        dbg("Preference change not implemented: {}\n".format(message_json['name']))


def process_user_change(message_json, eventrouter, team, channel, metadata):
    """
    Currently only used to update status, but lots here we could do.
    """
    user = metadata['user']
    profile = message_json['user']['profile']
    if user:
        user.update_status(profile.get('status_emoji'), profile.get('status_text'))
        dmchannel = team.find_channel_by_members({user.identifier}, channel_type='im')
        if dmchannel:
            dmchannel.set_topic(create_user_status_string(profile))


def process_user_typing(message_json, eventrouter, team, channel, metadata):
    if channel:
        channel.set_typing(metadata["user"].name)
        w.bar_item_update("slack_typing_notice")


def process_team_join(message_json, eventrouter, team, channel, metadata):
    user = message_json['user']
    team.users[user["id"]] = SlackUser(team.identifier, **user)


def process_pong(message_json, eventrouter, team, channel, metadata):
    team.last_pong_time = time.time()


def process_message(message_json, eventrouter, team, channel, metadata, history_message=False):
    if SlackTS(message_json["ts"]) in channel.messages:
        return

    if "thread_ts" in message_json and "reply_count" not in message_json and "subtype" not in message_json:
        if message_json.get("reply_broadcast"):
            message_json["subtype"] = "thread_broadcast"
        else:
            message_json["subtype"] = "thread_message"

    subtype = message_json.get("subtype")
    subtype_functions = get_functions_with_prefix("subprocess_")

    if subtype in subtype_functions:
        subtype_functions[subtype](message_json, eventrouter, team, channel, history_message)
    else:
        message = SlackMessage(message_json, team, channel)
        channel.store_message(message, team)

        text = channel.render(message)
        dbg("Rendered message: %s" % text)
        dbg("Sender: %s (%s)" % (message.sender, message.sender_plain))

        if subtype == 'me_message':
            prefix = w.prefix("action").rstrip()
        else:
            prefix = message.sender

        channel.buffer_prnt(prefix, text, message.ts, tag_nick=message.sender_plain, history_message=history_message)
        channel.unread_count_display += 1
        dbg("NORMAL REPLY {}".format(message_json))

    if not history_message:
        download_files(message_json, team)


def download_files(message_json, team):
    download_location = config.files_download_location
    if not download_location:
        return
    download_location = w.string_eval_path_home(download_location, {}, {}, {})

    if not os.path.exists(download_location):
        try:
            os.makedirs(download_location)
        except:
            w.prnt('', 'ERROR: Failed to create directory at files_download_location: {}'
                    .format(format_exc_only()))

    def fileout_iter(path):
        yield path
        main, ext = os.path.splitext(path)
        for i in count(start=1):
            yield main + "-{}".format(i) + ext

    for f in message_json.get('files', []):
        if f.get('mode') == 'tombstone':
            continue

        filetype = '' if f['title'].endswith(f['filetype']) else '.' + f['filetype']
        filename = '{}_{}{}'.format(team.preferred_name, f['title'], filetype)
        for fileout in fileout_iter(os.path.join(download_location, filename)):
            if os.path.isfile(fileout):
                continue
            w.hook_process_hashtable(
                "url:" + f['url_private'],
                {
                    'file_out': fileout,
                    'httpheader': 'Authorization: Bearer ' + team.token
                },
                config.slack_timeout, "", "")
            break


def subprocess_thread_message(message_json, eventrouter, team, channel, history_message):
    parent_ts = message_json.get('thread_ts')
    if parent_ts:
        parent_message = channel.messages.get(SlackTS(parent_ts))
        if parent_message:
            message = SlackThreadMessage(
                parent_message, message_json, team, channel)
            parent_message.submessages.append(message)
            channel.hash_message(parent_ts)
            channel.store_message(message, team)
            channel.change_message(parent_ts)

            if parent_message.thread_channel and parent_message.thread_channel.active:
                parent_message.thread_channel.buffer_prnt(message.sender, parent_message.thread_channel.render(message), message.ts, tag_nick=message.sender_plain)
            elif message.ts > channel.last_read and message.has_mention():
                parent_message.notify_thread(action="mention", sender_id=message_json["user"])

            if config.thread_messages_in_channel or message_json["subtype"] == "thread_broadcast":
                thread_tag = "thread_broadcast" if message_json["subtype"] == "thread_broadcast" else "thread_message"
                channel.buffer_prnt(
                    message.sender,
                    channel.render(message),
                    message.ts,
                    tag_nick=message.sender_plain,
                    history_message=history_message,
                    extra_tags=[thread_tag],
                )


subprocess_thread_broadcast = subprocess_thread_message


def subprocess_channel_join(message_json, eventrouter, team, channel, history_message):
    prefix_join = w.prefix("join").strip()
    message = SlackMessage(message_json, team, channel, override_sender=prefix_join)
    channel.buffer_prnt(prefix_join, channel.render(message), message_json["ts"], tagset='join', tag_nick=message.get_sender()[1], history_message=history_message)
    channel.user_joined(message_json['user'])
    channel.store_message(message, team)


def subprocess_channel_leave(message_json, eventrouter, team, channel, history_message):
    prefix_leave = w.prefix("quit").strip()
    message = SlackMessage(message_json, team, channel, override_sender=prefix_leave)
    channel.buffer_prnt(prefix_leave, channel.render(message), message_json["ts"], tagset='leave', tag_nick=message.get_sender()[1], history_message=history_message)
    channel.user_left(message_json['user'])
    channel.store_message(message, team)


def subprocess_channel_topic(message_json, eventrouter, team, channel, history_message):
    prefix_topic = w.prefix("network").strip()
    message = SlackMessage(message_json, team, channel, override_sender=prefix_topic)
    channel.buffer_prnt(prefix_topic, channel.render(message), message_json["ts"], tagset="topic", tag_nick=message.get_sender()[1], history_message=history_message)
    channel.set_topic(message_json["topic"])
    channel.store_message(message, team)


subprocess_group_join = subprocess_channel_join
subprocess_group_leave = subprocess_channel_leave
subprocess_group_topic = subprocess_channel_topic


def subprocess_message_replied(message_json, eventrouter, team, channel, history_message):
    parent_ts = message_json["message"].get("thread_ts")
    parent_message = channel.messages.get(SlackTS(parent_ts))
    # Thread exists but is not open yet
    if parent_message is not None \
            and not (parent_message.thread_channel and parent_message.thread_channel.active):
        channel.hash_message(parent_ts)
        last_message = max(message_json["message"]["replies"], key=lambda x: x["ts"])
        if message_json["message"].get("user") == team.myidentifier:
            parent_message.notify_thread(action="response", sender_id=last_message["user"])
        elif any(team.myidentifier == r["user"] for r in message_json["message"]["replies"]):
            parent_message.notify_thread(action="participant", sender_id=last_message["user"])


def subprocess_message_changed(message_json, eventrouter, team, channel, history_message):
    new_message = message_json.get("message")
    channel.change_message(new_message["ts"], message_json=new_message)


def subprocess_message_deleted(message_json, eventrouter, team, channel, history_message):
    message = colorize_string(config.color_deleted, '(deleted)')
    channel.change_message(message_json["deleted_ts"], text=message)


def process_reply(message_json, eventrouter, team, channel, metadata):
    reply_to = int(message_json["reply_to"])
    original_message_json = team.ws_replies.pop(reply_to, None)
    if original_message_json:
        original_message_json.update(message_json)
        channel = team.channels[original_message_json.get('channel')]
        process_message(original_message_json, eventrouter, team=team, channel=channel, metadata={})
        dbg("REPLY {}".format(message_json))
    else:
        dbg("Unexpected reply {}".format(message_json))


def process_channel_marked(message_json, eventrouter, team, channel, metadata):
    ts = message_json.get("ts")
    if ts:
        channel.mark_read(ts=ts, force=True, update_remote=False)
    else:
        dbg("tried to mark something weird {}".format(message_json))


process_group_marked = process_channel_marked
process_im_marked = process_channel_marked
process_mpim_marked = process_channel_marked


def process_channel_joined(message_json, eventrouter, team, channel, metadata):
    channel.update_from_message_json(message_json["channel"])
    channel.open()


def process_channel_created(message_json, eventrouter, team, channel, metadata):
    item = message_json["channel"]
    item['is_member'] = False
    channel = SlackChannel(eventrouter, team=team, **item)
    team.channels[item["id"]] = channel
    team.buffer_prnt('Channel created: {}'.format(channel.slack_name))


def process_channel_rename(message_json, eventrouter, team, channel, metadata):
    channel.slack_name = message_json['channel']['name']


def process_im_created(message_json, eventrouter, team, channel, metadata):
    item = message_json["channel"]
    channel = SlackDMChannel(eventrouter, team=team, users=team.users, **item)
    team.channels[item["id"]] = channel
    team.buffer_prnt('IM channel created: {}'.format(channel.name))


def process_im_open(message_json, eventrouter, team, channel, metadata):
    channel.check_should_open(True)
    w.buffer_set(channel.channel_buffer, "hotlist", "2")


def process_im_close(message_json, eventrouter, team, channel, metadata):
    if channel.channel_buffer:
        w.prnt(team.channel_buffer,
                'IM {} closed by another client or the server'.format(channel.name))
    eventrouter.weechat_controller.unregister_buffer(channel.channel_buffer, False, True)


def process_group_joined(message_json, eventrouter, team, channel, metadata):
    item = message_json["channel"]
    if item["name"].startswith("mpdm-"):
        channel = SlackMPDMChannel(eventrouter, team.users, team.myidentifier, team=team, **item)
    else:
        channel = SlackGroupChannel(eventrouter, team=team, **item)
    team.channels[item["id"]] = channel
    channel.open()


def process_reaction_added(message_json, eventrouter, team, channel, metadata):
    channel = team.channels.get(message_json["item"].get("channel"))
    if message_json["item"].get("type") == "message":
        ts = SlackTS(message_json['item']["ts"])

        message = channel.messages.get(ts)
        if message:
            message.add_reaction(message_json["reaction"], message_json["user"])
            channel.change_message(ts)
    else:
        dbg("reaction to item type not supported: " + str(message_json))


def process_reaction_removed(message_json, eventrouter, team, channel, metadata):
    channel = team.channels.get(message_json["item"].get("channel"))
    if message_json["item"].get("type") == "message":
        ts = SlackTS(message_json['item']["ts"])

        message = channel.messages.get(ts)
        if message:
            message.remove_reaction(message_json["reaction"], message_json["user"])
            channel.change_message(ts)
    else:
        dbg("Reaction to item type not supported: " + str(message_json))


def process_subteam_created(subteam_json, eventrouter, team, channel, metadata):
    subteam_json_info = subteam_json['subteam']
    is_member = team.myidentifier in subteam_json_info.get('users', [])
    subteam = SlackSubteam(team.identifier, is_member=is_member, **subteam_json_info)
    team.subteams[subteam_json_info['id']] = subteam


def process_subteam_updated(subteam_json, eventrouter, team, channel, metadata):
    current_subteam_info = team.subteams[subteam_json['subteam']['id']]
    is_member = team.myidentifier in subteam_json['subteam'].get('users', [])
    new_subteam_info = SlackSubteam(team.identifier, is_member=is_member, **subteam_json['subteam'])
    team.subteams[subteam_json['subteam']['id']] = new_subteam_info

    if current_subteam_info.is_member != new_subteam_info.is_member:
        for channel in team.channels.values():
            channel.set_highlights()

    if config.notify_usergroup_handle_updated and current_subteam_info.handle != new_subteam_info.handle:
        message = 'User group {old_handle} has updated its handle to {new_handle} in team {team}.'.format(
            name=current_subteam_info.handle, handle=new_subteam_info.handle, team=team.preferred_name)
        team.buffer_prnt(message, message=True)


def process_emoji_changed(message_json, eventrouter, team, channel, metadata):
    team.load_emoji_completions()


###### New module/global methods
def render_formatting(text):
    text = re.sub(r'(^| )\*([^*\n`]+)\*(?=[^\w]|$)',
                  r'\1{}*\2*{}'.format(w.color(config.render_bold_as),
                                       w.color('-' + config.render_bold_as)),
                  text,
                  flags=re.UNICODE)
    text = re.sub(r'(^| )_([^_\n`]+)_(?=[^\w]|$)',
                  r'\1{}_\2_{}'.format(w.color(config.render_italic_as),
                                       w.color('-' + config.render_italic_as)),
                  text,
                  flags=re.UNICODE)
    return text


def linkify_text(message, team, only_users=False):
    # The get_username_map function is a bit heavy, but this whole
    # function is only called on message send..
    usernames = team.get_username_map()
    channels = team.get_channel_map()
    usergroups = team.generate_usergroup_map()
    message_escaped = (message
        # Replace IRC formatting chars with Slack formatting chars.
        .replace('\x02', '*')
        .replace('\x1D', '_')
        .replace('\x1F', config.map_underline_to)
        # Escape chars that have special meaning to Slack. Note that we do not
        # (and should not) perform full HTML entity-encoding here.
        # See https://api.slack.com/docs/message-formatting for details.
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;'))

    def linkify_word(match):
        word = match.group(0)
        prefix, name = match.groups()
        if prefix == "@":
            if name in ["channel", "everyone", "group", "here"]:
                return "<!{}>".format(name)
            elif name in usernames:
                return "<@{}>".format(usernames[name])
            elif word in usergroups.keys():
                return "<!subteam^{}|{}>".format(usergroups[word], word)
        elif prefix == "#" and not only_users:
            if word in channels:
                return "<#{}|{}>".format(channels[word], name)
        return word

    linkify_regex = r'(?:^|(?<=\s))([@#])([\w\(\)\'.-]+)'
    return re.sub(linkify_regex, linkify_word, message_escaped, flags=re.UNICODE)


def unfurl_blocks(message_json):
    block_text = [""]
    for block in message_json["blocks"]:
        try:
            if block["type"] == "section":
                fields = block.get("fields", [])
                if "text" in block:
                    fields.insert(0, block["text"])
                block_text.extend(unfurl_block_element(field) for field in fields)
            elif block["type"] == "actions":
                elements = []
                for element in block["elements"]:
                    if element["type"] == "button":
                        elements.append(unfurl_block_element(element["text"]))
                    else:
                        elements.append(colorize_string(config.color_deleted,
                            '<<Unsupported block action type "{}">>'.format(element["type"])))
                block_text.append(" | ".join(elements))
            elif block["type"] == "call":
                block_text.append("Join via " + block["call"]["v1"]["join_url"])
            elif block["type"] == "divider":
                block_text.append("---")
            elif block["type"] == "context":
                block_text.append(" | ".join(unfurl_block_element(el) for el in block["elements"]))
            elif block["type"] == "image":
                if "title" in block:
                    block_text.append(unfurl_block_element(block["title"]))
                block_text.append(unfurl_block_element(block))
            elif block["type"] == "rich_text":
                continue
            else:
                block_text.append(colorize_string(config.color_deleted,
                    '<<Unsupported block type "{}">>'.format(block["type"])))
                dbg('Unsupported block: "{}"'.format(json.dumps(block)), level=4)
        except Exception as e:
            dbg("Failed to unfurl block ({}): {}".format(repr(e), json.dumps(block)), level=4)
    return "\n".join(block_text)


def unfurl_block_element(text):
    if text["type"] == "mrkdwn":
        return render_formatting(text["text"])
    elif text["type"] == "plain_text":
        return text["text"]
    elif text["type"] == "image":
        return "{} ({})".format(text["image_url"], text["alt_text"])


def unfurl_refs(text):
    """
    input : <@U096Q7CQM|someuser> has joined the channel
    ouput : someuser has joined the channel
    """
    # Find all strings enclosed by <>
    #  - <https://example.com|example with spaces>
    #  - <#C2147483705|#otherchannel>
    #  - <@U2147483697|@othernick>
    #  - <!subteam^U2147483697|@group>
    # Test patterns lives in ./_pytest/test_unfurl.py

    def unfurl_ref(match):
        ref, fallback = match.groups()

        resolved_ref = resolve_ref(ref)
        if resolved_ref != ref:
            return resolved_ref

        if fallback and not config.unfurl_ignore_alt_text:
            if ref.startswith("#"):
                return "#{}".format(fallback)
            elif ref.startswith("@"):
                return fallback
            elif ref.startswith("!subteam"):
                prefix = "@" if not fallback.startswith("@") else ""
                return prefix + fallback
            elif ref.startswith("!date"):
                return fallback
            else:
                match_url = r"^\w+:(//)?{}$".format(re.escape(fallback))
                url_matches_desc = re.match(match_url, ref)
                if url_matches_desc and config.unfurl_auto_link_display == "text":
                    return fallback
                elif url_matches_desc and config.unfurl_auto_link_display == "url":
                    return ref
                else:
                    return "{} ({})".format(ref, fallback)
        return ref

    return re.sub(r"<([^|>]*)(?:\|([^>]*))?>", unfurl_ref, text)


def unhtmlescape(text):
    return text.replace("&lt;", "<") \
               .replace("&gt;", ">") \
               .replace("&amp;", "&")


def unwrap_attachments(message_json, text_before):
    text_before_unescaped = unhtmlescape(text_before)
    attachment_texts = []
    a = message_json.get("attachments")
    if a:
        if text_before:
            attachment_texts.append('')
        for attachment in a:
            # Attachments should be rendered roughly like:
            #
            # $pretext
            # $author: (if rest of line is non-empty) $title ($title_link) OR $from_url
            # $author: (if no $author on previous line) $text
            # $fields
            t = []
            prepend_title_text = ''
            if 'author_name' in attachment:
                prepend_title_text = attachment['author_name'] + ": "
            if 'pretext' in attachment:
                t.append(attachment['pretext'])
            title = attachment.get('title')
            title_link = attachment.get('title_link', '')
            if title_link in text_before_unescaped:
                title_link = ''
            if title and title_link:
                t.append('%s%s (%s)' % (prepend_title_text, title, title_link,))
                prepend_title_text = ''
            elif title and not title_link:
                t.append('%s%s' % (prepend_title_text, title,))
                prepend_title_text = ''
            from_url = attachment.get('from_url', '')
            if from_url not in text_before_unescaped and from_url != title_link:
                t.append(from_url)

            atext = attachment.get("text")
            if atext:
                tx = re.sub(r' *\n[\n ]+', '\n', atext)
                t.append(prepend_title_text + tx)
                prepend_title_text = ''

            image_url = attachment.get('image_url', '')
            if image_url not in text_before_unescaped and image_url != title_link:
                t.append(image_url)

            fields = attachment.get("fields")
            if fields:
                for f in fields:
                    if f.get('title'):
                        t.append('%s %s' % (f['title'], f['value'],))
                    else:
                        t.append(f['value'])
            fallback = attachment.get("fallback")
            if t == [] and fallback:
                t.append(fallback)
            attachment_texts.append("\n".join([x.strip() for x in t if x]))
    return "\n".join(attachment_texts)


def unwrap_files(message_json, text_before):
    files_texts = []
    for f in message_json.get('files', []):
        if f.get('mode', '') != 'tombstone':
            text = '{} ({})'.format(f['url_private'], f['title'])
        else:
            text = colorize_string(config.color_deleted, '(This file was deleted.)')
        files_texts.append(text)

    if text_before:
        files_texts.insert(0, '')
    return "\n".join(files_texts)


def resolve_ref(ref):
    if ref in ['!channel', '!everyone', '!group', '!here']:
        return ref.replace('!', '@')
    for team in EVENTROUTER.teams.values():
        if ref.startswith('@'):
            user = team.users.get(ref[1:])
            if user:
                suffix = config.external_user_suffix if user.is_external else ''
                return '@{}{}'.format(user.name, suffix)
        elif ref.startswith('#'):
            channel = team.channels.get(ref[1:])
            if channel:
                return channel.name
        elif ref.startswith('!subteam'):
            _, subteam_id = ref.split('^')
            subteam = team.subteams.get(subteam_id)
            if subteam:
                return subteam.handle
        elif ref.startswith("!date"):
            parts = ref.split('^')
            ref_datetime = datetime.fromtimestamp(int(parts[1]))
            link_suffix = ' ({})'.format(parts[3]) if len(parts) > 3 else ''
            token_to_format = {
                    'date_num': '%Y-%m-%d',
                    'date': '%B %d, %Y',
                    'date_short': '%b %d, %Y',
                    'date_long': '%A, %B %d, %Y',
                    'time': '%H:%M',
                    'time_secs': '%H:%M:%S'
            }

            def replace_token(match):
                token = match.group(1)
                if token.startswith('date_') and token.endswith('_pretty'):
                    if ref_datetime.date() == date.today():
                        return 'today'
                    elif ref_datetime.date() == date.today() - timedelta(days=1):
                        return 'yesterday'
                    elif ref_datetime.date() == date.today() + timedelta(days=1):
                        return 'tomorrow'
                    else:
                        token = token.replace('_pretty', '')
                if token in token_to_format:
                    return ref_datetime.strftime(token_to_format[token])
                else:
                    return match.group(0)

            return re.sub(r"{([^}]+)}", replace_token, parts[2]) + link_suffix

    # Something else, just return as-is
    return ref


def create_user_status_string(profile):
    real_name = profile.get("real_name")
    status_emoji = replace_string_with_emoji(profile.get("status_emoji", ""))
    status_text = profile.get("status_text")
    if status_emoji or status_text:
        return "{} | {} {}".format(real_name, status_emoji, status_text)
    else:
        return real_name


def create_reaction_string(reaction, myidentifier):
    if config.show_reaction_nicks:
        nicks = [resolve_ref('@{}'.format(user)) for user in reaction['users']]
        users = '({})'.format(','.join(nicks))
    else:
        users = len(reaction['users'])
    reaction_string = ':{}:{}'.format(reaction['name'], users)
    if myidentifier in reaction['users']:
        return colorize_string(config.color_reaction_suffix_added_by_you, reaction_string,
                reset_color=config.color_reaction_suffix)
    else:
        return reaction_string


def create_reactions_string(reactions, myidentifier):
    reactions_with_users = [r for r in reactions if len(r['users']) > 0]
    reactions_string = ' '.join(create_reaction_string(r, myidentifier) for r in reactions_with_users)
    if reactions_string:
        return ' ' + colorize_string(config.color_reaction_suffix, '[{}]'.format(reactions_string))
    else:
        return ''


def hdata_line_ts(line_pointer):
    data = w.hdata_pointer(hdata.line, line_pointer, 'data')
    ts_major = w.hdata_time(hdata.line_data, data, 'date')
    ts_minor = w.hdata_time(hdata.line_data, data, 'date_printed')
    return (ts_major, ts_minor)


def modify_buffer_line(buffer_pointer, ts, new_text):
    own_lines = w.hdata_pointer(hdata.buffer, buffer_pointer, 'own_lines')
    line_pointer = w.hdata_pointer(hdata.lines, own_lines, 'last_line')

    # Find the last line with this ts
    while line_pointer and hdata_line_ts(line_pointer) != (ts.major, ts.minor):
        line_pointer = w.hdata_move(hdata.line, line_pointer, -1)

    # Find all lines for the message
    pointers = []
    while line_pointer and hdata_line_ts(line_pointer) == (ts.major, ts.minor):
        pointers.append(line_pointer)
        line_pointer = w.hdata_move(hdata.line, line_pointer, -1)
    pointers.reverse()

    # Split the message into at most the number of existing lines as we can't insert new lines
    lines = new_text.split('\n', len(pointers) - 1)
    # Replace newlines to prevent garbled lines in bare display mode
    lines = [line.replace('\n', ' | ') for line in lines]
    # Extend lines in case the new message is shorter than the old as we can't delete lines
    lines += [''] * (len(pointers) - len(lines))

    for pointer, line in zip(pointers, lines):
        data = w.hdata_pointer(hdata.line, pointer, 'data')
        w.hdata_update(hdata.line_data, data, {"message": line})

    return w.WEECHAT_RC_OK


def modify_last_print_time(buffer_pointer, ts_minor):
    """
    This overloads the time printed field to let us store the slack
    per message unique id that comes after the "." in a slack ts
    """
    own_lines = w.hdata_pointer(hdata.buffer, buffer_pointer, 'own_lines')
    line_pointer = w.hdata_pointer(hdata.lines, own_lines, 'last_line')

    while line_pointer:
        data = w.hdata_pointer(hdata.line, line_pointer, 'data')
        w.hdata_update(hdata.line_data, data, {"date_printed": str(ts_minor)})

        if w.hdata_string(hdata.line_data, data, 'prefix'):
            # Reached the first line of the message, so stop here
            break

        # Move one line backwards so all lines of the message are set
        line_pointer = w.hdata_move(hdata.line, line_pointer, -1)

    return w.WEECHAT_RC_OK


def nick_from_profile(profile, username):
    full_name = profile.get('real_name') or username
    if config.use_full_names:
        nick = full_name
    else:
        nick = profile.get('display_name') or full_name
    return nick.replace(' ', '')


def format_nick(nick, previous_nick=None):
    if nick == previous_nick:
        nick = w.config_string(w.config_get('weechat.look.prefix_same_nick')) or nick
    nick_prefix = w.config_string(w.config_get('weechat.look.nick_prefix'))
    nick_prefix_color_name = w.config_string(w.config_get('weechat.color.chat_nick_prefix'))

    nick_suffix = w.config_string(w.config_get('weechat.look.nick_suffix'))
    nick_suffix_color_name = w.config_string(w.config_get('weechat.color.chat_nick_prefix'))
    return colorize_string(nick_prefix_color_name, nick_prefix) + nick + colorize_string(nick_suffix_color_name, nick_suffix)


def tag(tagset=None, user=None, self_msg=False, backlog=False, no_log=False, extra_tags=None):
    tagsets = {
        "team_info": {"no_highlight", "log3"},
        "team_message": {"irc_privmsg", "notify_message", "log1"},
        "dm": {"irc_privmsg", "notify_private", "log1"},
        "join": {"irc_join", "no_highlight", "log4"},
        "leave": {"irc_part", "no_highlight", "log4"},
        "topic": {"irc_topic", "no_highlight", "log3"},
        "channel": {"irc_privmsg", "notify_message", "log1"},
    }
    nick_tag = {"nick_{}".format(user).replace(" ", "_")} if user else set()
    slack_tag = {"slack_{}".format(tagset or "default")}
    tags = nick_tag | slack_tag | tagsets.get(tagset, set())
    if self_msg or backlog:
        tags -= {"notify_highlight", "notify_message", "notify_private"}
        tags |= {"notify_none", "no_highlight"}
        if self_msg:
            tags |= {"self_msg"}
        if backlog:
            tags |= {"logger_backlog"}
    if no_log:
        tags |= {"no_log"}
        tags = {tag for tag in tags if not tag.startswith("log") or tag == "logger_backlog"}
    if extra_tags:
        tags |= set(extra_tags)
    return ",".join(tags)


def set_own_presence_active(team):
    slackbot = team.get_channel_map()['Slackbot']
    channel = team.channels[slackbot]
    request = {"type": "typing", "channel": channel.identifier}
    channel.team.send_to_websocket(request, expect_reply=False)


###### New/converted command_ commands


@slack_buffer_or_ignore
@utf8_decode
def invite_command_cb(data, current_buffer, args):
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
    split_args = args.split()[1:]
    if not split_args:
        w.prnt('', 'Too few arguments for command "/invite" (help on command: /help invite)')
        return w.WEECHAT_RC_OK_EAT

    if split_args[-1].startswith("#") or split_args[-1].startswith(config.group_name_prefix):
        nicks = split_args[:-1]
        channel = team.channels.get(team.get_channel_map().get(split_args[-1]))
        if not nicks or not channel:
            w.prnt('', '{}: No such nick/channel'.format(split_args[-1]))
            return w.WEECHAT_RC_OK_EAT
    else:
        nicks = split_args
        channel = EVENTROUTER.weechat_controller.buffers[current_buffer]

    all_users = team.get_username_map()
    users = set()
    for nick in nicks:
        user = all_users.get(nick.lstrip('@'))
        if not user:
            w.prnt('', 'ERROR: Unknown user: {}'.format(nick))
            return w.WEECHAT_RC_OK_EAT
        users.add(user)

    s = SlackRequest(team, "conversations.invite", {"channel": channel.identifier, "users": ",".join(users)},
            channel=channel, metadata={"nicks": nicks})
    EVENTROUTER.receive(s)
    return w.WEECHAT_RC_OK_EAT


@slack_buffer_or_ignore
@utf8_decode
def part_command_cb(data, current_buffer, args):
    e = EVENTROUTER
    args = args.split()
    if len(args) > 1:
        team = e.weechat_controller.buffers[current_buffer].team
        cmap = team.get_channel_map()
        channel = "".join(args[1:])
        if channel in cmap:
            buffer_ptr = team.channels[cmap[channel]].channel_buffer
            e.weechat_controller.unregister_buffer(buffer_ptr, update_remote=True, close_buffer=True)
        else:
            w.prnt(team.channel_buffer, "{}: No such channel".format(channel))
    else:
        e.weechat_controller.unregister_buffer(current_buffer, update_remote=True, close_buffer=True)
    return w.WEECHAT_RC_OK_EAT


def parse_topic_command(command):
    args = command.split()[1:]
    channel_name = None
    topic = None

    if args:
        if args[0].startswith('#'):
            channel_name = args[0]
            topic = args[1:]
        else:
            topic = args

    if topic == []:
        topic = None
    if topic:
        topic = ' '.join(topic)
    if topic == '-delete':
        topic = ''

    return channel_name, topic


@slack_buffer_or_ignore
@utf8_decode
def topic_command_cb(data, current_buffer, command):
    """
    Change the topic of a channel
    /topic [<channel>] [<topic>|-delete]
    """
    channel_name, topic = parse_topic_command(command)
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team

    if channel_name:
        channel = team.channels.get(team.get_channel_map().get(channel_name))
    else:
        channel = EVENTROUTER.weechat_controller.buffers[current_buffer]

    if not channel:
        w.prnt(team.channel_buffer, "{}: No such channel".format(channel_name))
        return w.WEECHAT_RC_OK_EAT

    if topic is None:
        w.prnt(channel.channel_buffer,
                'Topic for {} is "{}"'.format(channel.name, channel.render_topic()))
    else:
        s = SlackRequest(team, "conversations.setTopic",
                {"channel": channel.identifier, "topic": linkify_text(topic, team)}, channel=channel)
        EVENTROUTER.receive(s)
    return w.WEECHAT_RC_OK_EAT


@slack_buffer_or_ignore
@utf8_decode
def whois_command_cb(data, current_buffer, command):
    """
    Get real name of user
    /whois <nick>
    """
    args = command.split()
    if len(args) < 2:
        w.prnt(current_buffer, "Not enough arguments")
        return w.WEECHAT_RC_OK_EAT
    user = args[1]
    if (user.startswith('@')):
        user = user[1:]
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
    u = team.users.get(team.get_username_map().get(user))
    if u:
        def print_profile(field):
            value = u.profile.get(field)
            if value:
                team.buffer_prnt("[{}]: {}: {}".format(user, field, value))

        team.buffer_prnt("[{}]: {}".format(user, u.real_name))
        status_emoji = replace_string_with_emoji(u.profile.get("status_emoji", ""))
        status_text = u.profile.get("status_text", "")
        if status_emoji or status_text:
            team.buffer_prnt("[{}]: {} {}".format(user, status_emoji, status_text))

        team.buffer_prnt("[{}]: username: {}".format(user, u.username))
        team.buffer_prnt("[{}]: id: {}".format(user, u.identifier))

        print_profile('title')
        print_profile('email')
        print_profile('phone')
        print_profile('skype')
    else:
        team.buffer_prnt("[{}]: No such user".format(user))
    return w.WEECHAT_RC_OK_EAT


@slack_buffer_or_ignore
@utf8_decode
def me_command_cb(data, current_buffer, args):
    channel = EVENTROUTER.weechat_controller.buffers[current_buffer]
    message = args.split(' ', 1)[1]
    channel.send_message(message, subtype='me_message')
    return w.WEECHAT_RC_OK_EAT


@utf8_decode
def command_register(data, current_buffer, args):
    """
    /slack register [code/token]
    Register a Slack team in wee-slack. Call this without any arguments and
    follow the instructions to register a new team. If you already have a token
    for a team, you can call this with that token to add it.
    """
    CLIENT_ID = "2468770254.51917335286"
    CLIENT_SECRET = "dcb7fe380a000cba0cca3169a5fe8d70"  # Not really a secret.
    REDIRECT_URI = "https%3A%2F%2Fwee-slack.github.io%2Fwee-slack%2Foauth%23"
    if not args:
        message = textwrap.dedent("""
            ### Connecting to a Slack team with OAuth ###
            1) Paste this link into a browser: https://slack.com/oauth/authorize?client_id={}&scope=client&redirect_uri={}
            2) Select the team you wish to access from wee-slack in your browser. If you want to add multiple teams, you will have to repeat this whole process for each team.
            3) Click "Authorize" in the browser.
               If you get a message saying you are not authorized to install wee-slack, the team has restricted Slack app installation and you will have to request it from an admin. To do that, go to https://my.slack.com/apps/A1HSZ9V8E-wee-slack and click "Request to Install".
            4) The web page will show a command in the form `/slack register <code>`. Run this command in weechat.
        """).strip().format(CLIENT_ID, REDIRECT_URI)
        w.prnt("", message)
        return w.WEECHAT_RC_OK_EAT
    elif args.startswith('xox'):
        add_token(args)
        return w.WEECHAT_RC_OK_EAT

    uri = (
        "https://slack.com/api/oauth.access?"
        "client_id={}&client_secret={}&redirect_uri={}&code={}"
    ).format(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, args)
    params = {'useragent': 'wee_slack {}'.format(SCRIPT_VERSION)}
    w.hook_process_hashtable('url:', params, config.slack_timeout, "", "")
    w.hook_process_hashtable("url:{}".format(uri), params, config.slack_timeout, "register_callback", "")
    return w.WEECHAT_RC_OK_EAT


@utf8_decode
def register_callback(data, command, return_code, out, err):
    if return_code != 0:
        w.prnt("", "ERROR: problem when trying to get Slack OAuth token. Got return code {}. Err: {}".format(return_code, err))
        w.prnt("", "Check the network or proxy settings")
        return w.WEECHAT_RC_OK_EAT

    if len(out) <= 0:
        w.prnt("", "ERROR: problem when trying to get Slack OAuth token. Got 0 length answer. Err: {}".format(err))
        w.prnt("", "Check the network or proxy settings")
        return w.WEECHAT_RC_OK_EAT

    d = json.loads(out)
    if not d["ok"]:
        w.prnt("",
               "ERROR: Couldn't get Slack OAuth token: {}".format(d['error']))
        return w.WEECHAT_RC_OK_EAT

    add_token(d['access_token'], d['team_name'])
    return w.WEECHAT_RC_OK_EAT


def add_token(token, team_name=None):
    if config.is_default('slack_api_token'):
        w.config_set_plugin('slack_api_token', token)
    else:
        # Add new token to existing set, joined by comma.
        existing_tokens = config.get_string('slack_api_token')
        if token in existing_tokens:
            print_error('This token is already registered')
            return
        w.config_set_plugin('slack_api_token', ','.join([existing_tokens, token]))

    if team_name:
        w.prnt("", "Success! Added team \"{}\"".format(team_name))
    else:
        w.prnt("", "Success! Added token")
    w.prnt("", "Please reload wee-slack with: /python reload slack")
    w.prnt("", "If you want to add another team you can repeat this process from step 1 before reloading wee-slack.")


@slack_buffer_or_ignore
@utf8_decode
def msg_command_cb(data, current_buffer, args):
    aargs = args.split(None, 2)
    who = aargs[1].lstrip('@')
    if who == "*":
        who = EVENTROUTER.weechat_controller.buffers[current_buffer].name
    else:
        join_query_command_cb(data, current_buffer, '/query ' + who)

    if len(aargs) > 2:
        message = aargs[2]
        team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
        cmap = team.get_channel_map()
        if who in cmap:
            channel = team.channels[cmap[who]]
            channel.send_message(message)
    return w.WEECHAT_RC_OK_EAT


def print_team_items_info(team, header, items, extra_info_function):
    team.buffer_prnt("{}:".format(header))
    if items:
        max_name_length = max(len(item.name) for item in items)
        for item in sorted(items, key=lambda item: item.name.lower()):
            extra_info = extra_info_function(item)
            team.buffer_prnt("    {:<{}}({})".format(item.name, max_name_length + 2, extra_info))
    return w.WEECHAT_RC_OK_EAT


def print_users_info(team, header, users):
    def extra_info_function(user):
        external_text = ", external" if user.is_external else ""
        return user.presence + external_text
    return print_team_items_info(team, header, users, extra_info_function)


@slack_buffer_required
@utf8_decode
def command_teams(data, current_buffer, args):
    """
    /slack teams
    List the connected Slack teams.
    """
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
    teams = EVENTROUTER.teams.values()
    extra_info_function = lambda team: "token: {}".format(token_for_print(team.token))
    return print_team_items_info(team, "Slack teams", teams, extra_info_function)


@slack_buffer_required
@utf8_decode
def command_channels(data, current_buffer, args):
    """
    /slack channels
    List the channels in the current team.
    """
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
    channels = [channel for channel in team.channels.values() if channel.type not in ['im', 'mpim']]
    def extra_info_function(channel):
        if channel.active:
            return "member"
        elif getattr(channel, "is_archived", None):
            return "archived"
        else:
            return "not a member"
    return print_team_items_info(team, "Channels", channels, extra_info_function)


@slack_buffer_required
@utf8_decode
def command_users(data, current_buffer, args):
    """
    /slack users
    List the users in the current team.
    """
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
    return print_users_info(team, "Users", team.users.values())


@slack_buffer_required
@utf8_decode
def command_usergroups(data, current_buffer, args):
    """
    /slack usergroups [handle]
    List the usergroups in the current team
    If handle is given show the members in the usergroup
    """
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
    usergroups = team.generate_usergroup_map()
    usergroup_key = usergroups.get(args)

    if usergroup_key:
        s = SlackRequest(team, "usergroups.users.list", {"usergroup": usergroup_key},
                metadata={'usergroup_handle': args})
        EVENTROUTER.receive(s)
    elif args:
        w.prnt('', 'ERROR: Unknown usergroup handle: {}'.format(args))
        return w.WEECHAT_RC_ERROR
    else:
        def extra_info_function(subteam):
            is_member = 'member' if subteam.is_member else 'not a member'
            return '{}, {}'.format(subteam.handle, is_member)
        return print_team_items_info(team, "Usergroups", team.subteams.values(), extra_info_function)
    return w.WEECHAT_RC_OK_EAT

command_usergroups.completion = '%(usergroups)'


@slack_buffer_required
@utf8_decode
def command_talk(data, current_buffer, args):
    """
    /slack talk <user>[,<user2>[,<user3>...]]
    Open a chat with the specified user(s).
    """
    if not args:
        w.prnt('', 'Usage: /slack talk <user>[,<user2>[,<user3>...]]')
        return w.WEECHAT_RC_ERROR
    return join_query_command_cb(data, current_buffer, '/query ' + args)

command_talk.completion = '%(nicks)'


@slack_buffer_or_ignore
@utf8_decode
def join_query_command_cb(data, current_buffer, args):
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
    split_args = args.split(' ', 1)
    if len(split_args) < 2 or not split_args[1]:
        w.prnt('', 'Too few arguments for command "{}" (help on command: /help {})'
                .format(split_args[0], split_args[0].lstrip('/')))
        return w.WEECHAT_RC_OK_EAT
    query = split_args[1]

    # Try finding the channel by name
    channel = team.channels.get(team.get_channel_map().get(query))

    # If the channel doesn't exist, try finding a DM or MPDM instead
    if not channel:
        if query.startswith('#'):
            w.prnt('', 'ERROR: Unknown channel: {}'.format(query))
            return w.WEECHAT_RC_OK_EAT

        # Get the IDs of the users
        all_users = team.get_username_map()
        users = set()
        for username in query.split(','):
            user = all_users.get(username.lstrip('@'))
            if not user:
                w.prnt('', 'ERROR: Unknown user: {}'.format(username))
                return w.WEECHAT_RC_OK_EAT
            users.add(user)

        if users:
            if len(users) > 1:
                channel_type = 'mpim'
                # Add the current user since MPDMs include them as a member
                users.add(team.myidentifier)
            else:
                channel_type = 'im'

            channel = team.find_channel_by_members(users, channel_type=channel_type)

            # If the DM or MPDM doesn't exist, create it
            if not channel:
                s = SlackRequest(team, SLACK_API_TRANSLATOR[channel_type]['join'],
                        {'users': ','.join(users)})
                EVENTROUTER.receive(s)

    if channel:
        channel.open()
        if config.switch_buffer_on_join:
            w.buffer_set(channel.channel_buffer, "display", "1")
    return w.WEECHAT_RC_OK_EAT


@slack_buffer_required
@utf8_decode
def command_showmuted(data, current_buffer, args):
    """
    /slack showmuted
    List the muted channels in the current team.
    """
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
    muted_channels = [team.channels[key].name
            for key in team.muted_channels if key in team.channels]
    team.buffer_prnt("Muted channels: {}".format(', '.join(muted_channels)))
    return w.WEECHAT_RC_OK_EAT


def get_msg_from_id(channel, msg_id):
    if msg_id[0] == '$':
        msg_id = msg_id[1:]
    ts = channel.hashed_messages.get(msg_id)
    return channel.messages.get(ts)


@slack_buffer_required
@utf8_decode
def command_thread(data, current_buffer, args):
    """
    /thread [message_id]
    Open the thread for the message.
    If no message id is specified the last thread in channel will be opened.
    """
    channel = EVENTROUTER.weechat_controller.buffers[current_buffer]

    if not isinstance(channel, SlackChannelCommon):
        print_error('/thread can not be used in the team buffer, only in a channel')
        return w.WEECHAT_RC_ERROR

    if args:
        msg = get_msg_from_id(channel, args)
        if not msg:
            w.prnt('', 'ERROR: Invalid id given, must be an existing id')
            return w.WEECHAT_RC_OK_EAT
    else:
        for message in reversed(channel.messages.values()):
            if type(message) == SlackMessage and message.number_of_replies():
                msg = message
                break
        else:
            w.prnt('', 'ERROR: No threads found in channel')
            return w.WEECHAT_RC_OK_EAT

    msg.open_thread(switch=config.switch_buffer_on_join)
    return w.WEECHAT_RC_OK_EAT

command_thread.completion = '%(threads)'


@slack_buffer_required
@utf8_decode
def command_reply(data, current_buffer, args):
    """
    /reply [-alsochannel] [<count/message_id>] <message>

    When in a channel buffer:
    /reply [-alsochannel] <count/message_id> <message>
    Reply in a thread on the message. Specify either the message id or a count
    upwards to the message from the last message.

    When in a thread buffer:
    /reply [-alsochannel] <message>
    Reply to the current thread.  This can be used to send the reply to the
    rest of the channel.

    In either case, -alsochannel also sends the reply to the parent channel.
    """
    channel = EVENTROUTER.weechat_controller.buffers[current_buffer]
    parts = args.split(None, 1)
    if parts[0] == "-alsochannel":
        args = parts[1]
        broadcast = True
    else:
        broadcast = False

    if isinstance(channel, SlackThreadChannel):
        text = args
        msg = channel.parent_message
    else:
        try:
            msg_id, text = args.split(None, 1)
        except ValueError:
            w.prnt('', 'Usage (when in a channel buffer): /reply [-alsochannel] <count/message_id> <message>')
            return w.WEECHAT_RC_OK_EAT
        msg = get_msg_from_id(channel, msg_id)

    if msg:
        if isinstance(msg, SlackThreadMessage):
            parent_id = str(msg.parent_message.ts)
        else:
            parent_id = str(msg.ts)
    elif msg_id.isdigit() and int(msg_id) >= 1:
        mkeys = channel.main_message_keys_reversed()
        parent_id = str(next(islice(mkeys, int(msg_id) - 1, None)))
    else:
        w.prnt('', 'ERROR: Invalid id given, must be a number greater than 0 or an existing id')
        return w.WEECHAT_RC_OK_EAT

    channel.send_message(text, request_dict_ext={'thread_ts': parent_id, 'reply_broadcast': broadcast})
    return w.WEECHAT_RC_OK_EAT

command_reply.completion = '-alsochannel %(threads)||%(threads)'


@slack_buffer_required
@utf8_decode
def command_rehistory(data, current_buffer, args):
    """
    /rehistory
    Reload the history in the current channel.
    """
    channel = EVENTROUTER.weechat_controller.buffers[current_buffer]
    channel.clear_messages()
    channel.get_history()
    return w.WEECHAT_RC_OK_EAT


@slack_buffer_required
@utf8_decode
def command_hide(data, current_buffer, args):
    """
    /hide
    Hide the current channel if it is marked as distracting.
    """
    channel = EVENTROUTER.weechat_controller.buffers[current_buffer]
    name = channel.formatted_name(style='long_default')
    if name in config.distracting_channels:
        w.buffer_set(channel.channel_buffer, "hidden", "1")
    return w.WEECHAT_RC_OK_EAT


@utf8_decode
def slack_command_cb(data, current_buffer, args):
    split_args = args.split(' ', 1)
    cmd_name = split_args[0]
    cmd_args = split_args[1] if len(split_args) > 1 else ''
    cmd = EVENTROUTER.cmds.get(cmd_name or 'help')
    if not cmd:
        w.prnt('', 'Command not found: ' + cmd_name)
        return w.WEECHAT_RC_OK
    return cmd(data, current_buffer, cmd_args)


@utf8_decode
def command_help(data, current_buffer, args):
    """
    /slack help [command]
    Print help for /slack commands.
    """
    if args:
        cmd = EVENTROUTER.cmds.get(args)
        if cmd:
            cmds = {args: cmd}
        else:
            w.prnt('', 'Command not found: ' + args)
            return w.WEECHAT_RC_OK
    else:
        cmds = EVENTROUTER.cmds
        w.prnt('', '\n{}'.format(colorize_string('bold', 'Slack commands:')))

    script_prefix = '{0}[{1}python{0}/{1}slack{0}]{1}'.format(w.color('green'), w.color('reset'))

    for _, cmd in sorted(cmds.items()):
        name, cmd_args, description = parse_help_docstring(cmd)
        w.prnt('', '\n{}  {} {}\n\n{}'.format(
            script_prefix, colorize_string('white', name), cmd_args, description))
    return w.WEECHAT_RC_OK


@slack_buffer_required
@utf8_decode
def command_distracting(data, current_buffer, args):
    """
    /slack distracting
    Add or remove the current channel from distracting channels. You can hide
    or unhide these channels with /slack nodistractions.
    """
    channel = EVENTROUTER.weechat_controller.buffers[current_buffer]
    fullname = channel.formatted_name(style="long_default")
    if fullname in config.distracting_channels:
        config.distracting_channels.remove(fullname)
    else:
        config.distracting_channels.append(fullname)
    w.config_set_plugin('distracting_channels', ','.join(config.distracting_channels))
    return w.WEECHAT_RC_OK_EAT


@slack_buffer_required
@utf8_decode
def command_slash(data, current_buffer, args):
    """
    /slack slash /customcommand arg1 arg2 arg3
    Run a custom slack command.
    """
    channel = EVENTROUTER.weechat_controller.buffers[current_buffer]
    team = channel.team

    split_args = args.split(' ', 1)
    command = split_args[0]
    text = split_args[1] if len(split_args) > 1 else ""
    text_linkified = linkify_text(text, team, only_users=True)

    s = SlackRequest(team, "chat.command",
            {"command": command, "text": text_linkified, 'channel': channel.identifier},
            channel=channel, metadata={'command': command, 'command_args': text})
    EVENTROUTER.receive(s)
    return w.WEECHAT_RC_OK_EAT


@slack_buffer_required
@utf8_decode
def command_mute(data, current_buffer, args):
    """
    /slack mute
    Toggle mute on the current channel.
    """
    channel = EVENTROUTER.weechat_controller.buffers[current_buffer]
    team = channel.team
    team.muted_channels ^= {channel.identifier}
    muted_str = "Muted" if channel.identifier in team.muted_channels else "Unmuted"
    team.buffer_prnt("{} channel {}".format(muted_str, channel.name))
    s = SlackRequest(team, "users.prefs.set",
            {"name": "muted_channels", "value": ",".join(team.muted_channels)}, channel=channel)
    EVENTROUTER.receive(s)
    return w.WEECHAT_RC_OK_EAT


@slack_buffer_required
@utf8_decode
def command_linkarchive(data, current_buffer, args):
    """
    /slack linkarchive [message_id]
    Place a link to the channel or message in the input bar.
    Use cursor or mouse mode to get the id.
    """
    channel = EVENTROUTER.weechat_controller.buffers[current_buffer]
    url = 'https://{}/'.format(channel.team.domain)

    if isinstance(channel, SlackChannelCommon):
        url += 'archives/{}/'.format(channel.identifier)
        if args:
            if args[0] == '$':
                message_id = args[1:]
            else:
                message_id = args
            ts = channel.hashed_messages.get(message_id)
            message = channel.messages.get(ts)
            if message:
                url += 'p{}{:0>6}'.format(message.ts.majorstr(), message.ts.minorstr())
                if isinstance(message, SlackThreadMessage):
                    url += "?thread_ts={}&cid={}".format(message.parent_message.ts, channel.identifier)
            else:
                w.prnt('', 'ERROR: Invalid id given, must be an existing id')
                return w.WEECHAT_RC_OK_EAT

    w.command(current_buffer, "/input insert {}".format(url))
    return w.WEECHAT_RC_OK_EAT

command_linkarchive.completion = '%(threads)'


@utf8_decode
def command_nodistractions(data, current_buffer, args):
    """
    /slack nodistractions
    Hide or unhide all channels marked as distracting.
    """
    global hide_distractions
    hide_distractions = not hide_distractions
    channels = [channel for channel in EVENTROUTER.weechat_controller.buffers.values()
            if channel in config.distracting_channels]
    for channel in channels:
        w.buffer_set(channel.channel_buffer, "hidden", str(int(hide_distractions)))
    return w.WEECHAT_RC_OK_EAT


@slack_buffer_required
@utf8_decode
def command_upload(data, current_buffer, args):
    """
    /slack upload <filename>
    Uploads a file to the current buffer.
    """
    channel = EVENTROUTER.weechat_controller.buffers[current_buffer]
    weechat_dir = w.info_get("weechat_dir", "")
    file_path = os.path.join(weechat_dir, os.path.expanduser(args))

    if channel.type == 'team':
        w.prnt('', "ERROR: Can't upload a file to the team buffer")
        return w.WEECHAT_RC_ERROR

    if not os.path.isfile(file_path):
        unescaped_file_path = file_path.replace(r'\ ', ' ')
        if os.path.isfile(unescaped_file_path):
            file_path = unescaped_file_path
        else:
            w.prnt('', 'ERROR: Could not find file: {}'.format(file_path))
            return w.WEECHAT_RC_ERROR

    post_data = {
        'channels': channel.identifier,
    }
    if isinstance(channel, SlackThreadChannel):
        post_data['thread_ts'] = channel.parent_message.ts

    url = SlackRequest(channel.team, 'files.upload', post_data, channel=channel).request_string()
    options = [
        '-s',
        '-Ffile=@{}'.format(file_path),
        url
    ]

    proxy_string = ProxyWrapper().curl()
    if proxy_string:
        options.append(proxy_string)

    options_hashtable = {'arg{}'.format(i + 1): arg for i, arg in enumerate(options)}
    w.hook_process_hashtable('curl', options_hashtable, config.slack_timeout, 'upload_callback', '')
    return w.WEECHAT_RC_OK_EAT

command_upload.completion = '%(filename)'


@utf8_decode
def upload_callback(data, command, return_code, out, err):
    if return_code != 0:
        w.prnt("", "ERROR: Couldn't upload file. Got return code {}. Error: {}".format(return_code, err))
        return w.WEECHAT_RC_OK_EAT

    try:
        response = json.loads(out)
    except JSONDecodeError:
        w.prnt("", "ERROR: Couldn't process response from file upload. Got: {}".format(out))
        return w.WEECHAT_RC_OK_EAT

    if not response["ok"]:
        w.prnt("", "ERROR: Couldn't upload file. Error: {}".format(response["error"]))
    return w.WEECHAT_RC_OK_EAT


@utf8_decode
def away_command_cb(data, current_buffer, args):
    all_servers, message = re.match('^/away( -all)? ?(.*)', args).groups()
    if all_servers:
        team_buffers = [team.channel_buffer for team in EVENTROUTER.teams.values()]
    elif current_buffer in EVENTROUTER.weechat_controller.buffers:
        team_buffers = [current_buffer]
    else:
        return w.WEECHAT_RC_OK

    for team_buffer in team_buffers:
        if message:
            command_away(data, team_buffer, args)
        else:
            command_back(data, team_buffer, args)
    return w.WEECHAT_RC_OK


@slack_buffer_required
@utf8_decode
def command_away(data, current_buffer, args):
    """
    /slack away
    Sets your status as 'away'.
    """
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
    s = SlackRequest(team, "users.setPresence", {"presence": "away"})
    EVENTROUTER.receive(s)
    return w.WEECHAT_RC_OK


@slack_buffer_required
@utf8_decode
def command_status(data, current_buffer, args):
    """
    /slack status [<emoji> [<status_message>]|-delete]
    Lets you set your Slack Status (not to be confused with away/here).
    Prints current status if no arguments are given, unsets the status if -delete is given.
    """
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team

    split_args = args.split(" ", 1)
    if not split_args[0]:
        profile = team.users[team.myidentifier].profile
        team.buffer_prnt("Status: {} {}".format(
            replace_string_with_emoji(profile.get("status_emoji", "")),
            profile.get("status_text", "")))
        return w.WEECHAT_RC_OK

    emoji = "" if split_args[0] == "-delete" else split_args[0]
    text = split_args[1] if len(split_args) > 1 else ""
    new_profile = {"status_text": text, "status_emoji": emoji}

    s = SlackRequest(team, "users.profile.set", {"profile": new_profile})
    EVENTROUTER.receive(s)
    return w.WEECHAT_RC_OK

command_status.completion = "-delete|%(emoji)"


@utf8_decode
def line_event_cb(data, signal, hashtable):
    buffer_pointer = hashtable["_buffer"]
    line_timestamp = hashtable["_chat_line_date"]
    line_time_id = hashtable["_chat_line_date_printed"]
    channel = EVENTROUTER.weechat_controller.buffers.get(buffer_pointer)

    if line_timestamp and line_time_id and isinstance(channel, SlackChannelCommon):
        ts = SlackTS("{}.{}".format(line_timestamp, line_time_id))

        message_hash = channel.hash_message(ts)
        if message_hash is None:
            return w.WEECHAT_RC_OK
        message_hash = "$" + message_hash

        if data == "message":
            w.command(buffer_pointer, "/cursor stop")
            w.command(buffer_pointer, "/input insert {}".format(message_hash))
        elif data == "delete":
            w.command(buffer_pointer, "/input send {}s///".format(message_hash))
        elif data == "linkarchive":
            w.command(buffer_pointer, "/cursor stop")
            w.command(buffer_pointer, "/slack linkarchive {}".format(message_hash[1:]))
        elif data == "reply":
            w.command(buffer_pointer, "/cursor stop")
            w.command(buffer_pointer, "/input insert /reply {}\\x20".format(message_hash))
        elif data == "thread":
            w.command(buffer_pointer, "/cursor stop")
            w.command(buffer_pointer, "/thread {}".format(message_hash))
    return w.WEECHAT_RC_OK


@slack_buffer_required
@utf8_decode
def command_back(data, current_buffer, args):
    """
    /slack back
    Sets your status as 'back'.
    """
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
    s = SlackRequest(team, "users.setPresence", {"presence": "auto"})
    EVENTROUTER.receive(s)
    set_own_presence_active(team)
    return w.WEECHAT_RC_OK


@slack_buffer_required
@utf8_decode
def command_label(data, current_buffer, args):
    """
    /label <name>
    Rename a thread buffer. Note that this is not permanent. It will only last
    as long as you keep the buffer and wee-slack open.
    """
    channel = EVENTROUTER.weechat_controller.buffers[current_buffer]
    if channel.type == 'thread':
        new_name = " +" + args
        channel.label = new_name
        w.buffer_set(channel.channel_buffer, "short_name", new_name)
    return w.WEECHAT_RC_OK


@utf8_decode
def set_unread_cb(data, current_buffer, command):
    for channel in EVENTROUTER.weechat_controller.buffers.values():
        channel.mark_read()
    return w.WEECHAT_RC_OK


@slack_buffer_or_ignore
@utf8_decode
def set_unread_current_buffer_cb(data, current_buffer, command):
    channel = EVENTROUTER.weechat_controller.buffers[current_buffer]
    channel.mark_read()
    return w.WEECHAT_RC_OK


###### NEW EXCEPTIONS


class InvalidType(Exception):
    """
    Raised when we do type checking to ensure objects of the wrong
    type are not used improperly.
    """
    def __init__(self, type_str):
        super(InvalidType, self).__init__(type_str)

###### New but probably old and need to migrate


def closed_slack_debug_buffer_cb(data, buffer):
    global slack_debug
    slack_debug = None
    return w.WEECHAT_RC_OK


def create_slack_debug_buffer():
    global slack_debug, debug_string
    if slack_debug is None:
        debug_string = None
        slack_debug = w.buffer_new("slack-debug", "", "", "closed_slack_debug_buffer_cb", "")
        w.buffer_set(slack_debug, "notify", "0")
        w.buffer_set(slack_debug, "highlight_tags_restrict", "highlight_force")


def load_emoji():
    try:
        DIR = w.info_get('weechat_dir', '')
        with open('{}/weemoji.json'.format(DIR), 'r') as ef:
            emojis = json.loads(ef.read())
            if 'emoji' in emojis:
                print_error('The weemoji.json file is in an old format. Please update it.')
            else:
                emoji_unicode = {key: value['unicode'] for key, value in emojis.items()}

                emoji_skin_tones = {skin_tone['name']: skin_tone['unicode']
                        for emoji in emojis.values()
                        for skin_tone in emoji.get('skinVariations', {}).values()}

                emoji_with_skin_tones = chain(emoji_unicode.items(), emoji_skin_tones.items())
                emoji_with_skin_tones_reverse = {v: k for k, v in emoji_with_skin_tones}
                return emoji_unicode, emoji_with_skin_tones_reverse
    except:
        dbg("Couldn't load emoji list: {}".format(format_exc_only()), 5)
    return {}, {}


def parse_help_docstring(cmd):
    doc = textwrap.dedent(cmd.__doc__).strip().split('\n', 1)
    cmd_line = doc[0].split(None, 1)
    args = ''.join(cmd_line[1:])
    return cmd_line[0], args, doc[1].strip()


def setup_hooks():
    w.bar_item_new('slack_typing_notice', '(extra)typing_bar_item_cb', '')
    w.bar_item_new('away', '(extra)away_bar_item_cb', '')
    w.bar_item_new('slack_away', '(extra)away_bar_item_cb', '')

    w.hook_timer(5000, 0, 0, "ws_ping_cb", "")
    w.hook_timer(1000, 0, 0, "typing_update_cb", "")
    w.hook_timer(1000, 0, 0, "buffer_list_update_callback", "EVENTROUTER")
    w.hook_timer(3000, 0, 0, "reconnect_callback", "EVENTROUTER")
    w.hook_timer(1000 * 60 * 5, 0, 0, "slack_never_away_cb", "")

    w.hook_signal('buffer_closing', "buffer_closing_callback", "")
    w.hook_signal('buffer_switch', "buffer_switch_callback", "EVENTROUTER")
    w.hook_signal('window_switch', "buffer_switch_callback", "EVENTROUTER")
    w.hook_signal('quit', "quit_notification_callback", "")
    if config.send_typing_notice:
        w.hook_signal('input_text_changed', "typing_notification_cb", "")

    command_help.completion = '|'.join(EVENTROUTER.cmds.keys())
    completions = '||'.join(
            '{} {}'.format(name, getattr(cmd, 'completion', ''))
            for name, cmd in EVENTROUTER.cmds.items())

    w.hook_command(
        # Command name and description
        'slack', 'Plugin to allow typing notification and sync of read markers for slack.com',
        # Usage
        '<command> [<command options>]',
        # Description of arguments
        'Commands:\n' +
        '\n'.join(sorted(EVENTROUTER.cmds.keys())) +
        '\nUse /slack help <command> to find out more\n',
        # Completions
        completions,
        # Function name
        'slack_command_cb', '')

    w.hook_command_run('/me', 'me_command_cb', '')
    w.hook_command_run('/query', 'join_query_command_cb', '')
    w.hook_command_run('/join', 'join_query_command_cb', '')
    w.hook_command_run('/part', 'part_command_cb', '')
    w.hook_command_run('/topic', 'topic_command_cb', '')
    w.hook_command_run('/msg', 'msg_command_cb', '')
    w.hook_command_run('/invite', 'invite_command_cb', '')
    w.hook_command_run("/input complete_next", "complete_next_cb", "")
    w.hook_command_run("/input set_unread", "set_unread_cb", "")
    w.hook_command_run("/input set_unread_current_buffer", "set_unread_current_buffer_cb", "")
    w.hook_command_run('/away', 'away_command_cb', '')
    w.hook_command_run('/whois', 'whois_command_cb', '')

    for cmd_name in ['hide', 'label', 'rehistory', 'reply', 'thread']:
        cmd = EVENTROUTER.cmds[cmd_name]
        _, args, description = parse_help_docstring(cmd)
        completion = getattr(cmd, 'completion', '')
        w.hook_command(cmd_name, description, args, '', completion, 'command_' + cmd_name, '')

    w.hook_completion("irc_channel_topic", "complete topic for slack", "topic_completion_cb", "")
    w.hook_completion("irc_channels", "complete channels for slack", "channel_completion_cb", "")
    w.hook_completion("irc_privates", "complete dms/mpdms for slack", "dm_completion_cb", "")
    w.hook_completion("nicks", "complete @-nicks for slack", "nick_completion_cb", "")
    w.hook_completion("threads", "complete thread ids for slack", "thread_completion_cb", "")
    w.hook_completion("usergroups", "complete @-usergroups for slack", "usergroups_completion_cb", "")
    w.hook_completion("emoji", "complete :emoji: for slack", "emoji_completion_cb", "")

    w.key_bind("mouse", {
        "@chat(python.*):button2": "hsignal:slack_mouse",
        })
    w.key_bind("cursor", {
        "@chat(python.*):D": "hsignal:slack_cursor_delete",
        "@chat(python.*):L": "hsignal:slack_cursor_linkarchive",
        "@chat(python.*):M": "hsignal:slack_cursor_message",
        "@chat(python.*):R": "hsignal:slack_cursor_reply",
        "@chat(python.*):T": "hsignal:slack_cursor_thread",
        })

    w.hook_hsignal("slack_mouse", "line_event_cb", "message")
    w.hook_hsignal("slack_cursor_delete", "line_event_cb", "delete")
    w.hook_hsignal("slack_cursor_linkarchive", "line_event_cb", "linkarchive")
    w.hook_hsignal("slack_cursor_message", "line_event_cb", "message")
    w.hook_hsignal("slack_cursor_reply", "line_event_cb", "reply")
    w.hook_hsignal("slack_cursor_thread", "line_event_cb", "thread")

    # Hooks to fix/implement
    # w.hook_signal('buffer_opened', "buffer_opened_cb", "")
    # w.hook_signal('window_scrolled', "scrolled_cb", "")
    # w.hook_timer(3000, 0, 0, "slack_connection_persistence_cb", "")

##### END NEW


def dbg(message, level=0, main_buffer=False, fout=False):
    """
    send debug output to the slack-debug buffer and optionally write to a file.
    """
    # TODO: do this smarter
    if level >= config.debug_level:
        global debug_string
        message = "DEBUG: {}".format(message)
        if fout:
            with open('/tmp/debug.log', 'a+') as log_file:
                log_file.writelines(message + '\n')
        if main_buffer:
                w.prnt("", "slack: " + message)
        else:
            if slack_debug and (not debug_string or debug_string in message):
                w.prnt(slack_debug, message)


###### Config code
class PluginConfig(object):
    Setting = collections.namedtuple('Setting', ['default', 'desc'])
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
        'auto_open_threads': Setting(
            default='false',
            desc='Automatically open threads when mentioned or in'
            'response to own messages.'),
        'background_load_all_history': Setting(
            default='false',
            desc='Load history for each channel in the background as soon as it'
            ' opens, rather than waiting for the user to look at it.'),
        'channel_name_typing_indicator': Setting(
            default='true',
            desc='Change the prefix of a channel from # to > when someone is'
            ' typing in it. Note that this will (temporarily) affect the sort'
            ' order if you sort buffers by name rather than by number.'),
        'color_buflist_muted_channels': Setting(
            default='darkgray',
            desc='Color to use for muted channels in the buflist'),
        'color_deleted': Setting(
            default='red',
            desc='Color to use for deleted messages and files.'),
        'color_edited_suffix': Setting(
            default='095',
            desc='Color to use for (edited) suffix on messages that have been edited.'),
        'color_reaction_suffix': Setting(
            default='darkgray',
            desc='Color to use for the [:wave:(@user)] suffix on messages that'
            ' have reactions attached to them.'),
        'color_reaction_suffix_added_by_you': Setting(
            default='blue',
            desc='Color to use for reactions that you have added.'),
        'color_thread_suffix': Setting(
            default='lightcyan',
            desc='Color to use for the [thread: XXX] suffix on messages that'
            ' have threads attached to them. The special value "multiple" can'
            ' be used to use a different color for each thread.'),
        'color_typing_notice': Setting(
            default='yellow',
            desc='Color to use for the typing notice.'),
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
        'external_user_suffix': Setting(
            default='*',
            desc='The suffix appended to nicks to indicate external users.'),
        'files_download_location': Setting(
            default='',
            desc='If set, file attachments will be automatically downloaded'
            ' to this location. "%h" will be replaced by WeeChat home,'
            ' "~/.weechat" by default.'),
        'group_name_prefix': Setting(
            default='&',
            desc='The prefix of buffer names for groups (private channels).'),
        'map_underline_to': Setting(
            default='_',
            desc='When sending underlined text to slack, use this formatting'
            ' character for it. The default ("_") sends it as italics. Use'
            ' "*" to send bold instead.'),
        'muted_channels_activity': Setting(
            default='personal_highlights',
            desc="Control which activity you see from muted channels, either"
            " none, personal_highlights, all_highlights or all. none: Don't"
            " show any activity. personal_highlights: Only show personal"
            " highlights, i.e. not @channel and @here. all_highlights: Show"
            " all highlights, but not other messages. all: Show all activity,"
            " like other channels."),
        'notify_usergroup_handle_updated': Setting(
            default='false',
            desc="Control if you want to see notification when a usergroup's"
            " handle has changed, either true or false."),
        'never_away': Setting(
            default='false',
            desc='Poke Slack every five minutes so that it never marks you "away".'),
        'record_events': Setting(
            default='false',
            desc='Log all traffic from Slack to disk as JSON.'),
        'render_bold_as': Setting(
            default='bold',
            desc='When receiving bold text from Slack, render it as this in weechat.'),
        'render_emoji_as_string': Setting(
            default='false',
            desc="Render emojis as :emoji_name: instead of emoji characters. Enable this"
            " if your terminal doesn't support emojis, or set to 'both' if you want to"
            " see both renderings. Note that even though this is"
            " disabled by default, you need to place {}/blob/master/weemoji.json in your"
            " weechat directory to enable rendering emojis as emoji characters."
            .format(REPO_URL)),
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
        'shared_name_prefix': Setting(
            default='%',
            desc='The prefix of buffer names for shared channels.'),
        'short_buffer_names': Setting(
            default='false',
            desc='Use `foo.#channel` rather than `foo.slack.com.#channel` as the'
            ' internal name for Slack buffers.'),
        'show_buflist_presence': Setting(
            default='true',
            desc='Display a `+` character in the buffer list for present users.'),
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
        'thread_messages_in_channel': Setting(
            default='false',
            desc='When enabled shows thread messages in the parent channel.'),
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
        'use_full_names': Setting(
            default='false',
            desc='Use full names as the nicks for all users. When this is'
            ' false (the default), display names will be used if set, with a'
            ' fallback to the full name if display name is not set.'),
    }

    # Set missing settings to their defaults. Load non-missing settings from
    # weechat configs.
    def __init__(self):
        self.settings = {}
        # Set all descriptions, replace the values in the dict with the
        # default setting value rather than the (setting,desc) tuple.
        for key, (default, desc) in self.default_settings.items():
            w.config_set_desc_plugin(key, desc)
            self.settings[key] = default

        # Migrate settings from old versions of Weeslack...
        self.migrate()
        # ...and then set anything left over from the defaults.
        for key, default in self.settings.items():
            if not w.config_get_plugin(key):
                w.config_set_plugin(key, default)
        self.config_changed(None, None, None)

    def __str__(self):
        return "".join([x + "\t" + str(self.settings[x]) + "\n" for x in self.settings.keys()])

    def config_changed(self, data, key, value):
        for key in self.settings:
            self.settings[key] = self.fetch_setting(key)
        if self.debug_mode:
            create_slack_debug_buffer()
        return w.WEECHAT_RC_OK

    def fetch_setting(self, key):
        try:
            return getattr(self, 'get_' + key)(key)
        except AttributeError:
            # Most settings are on/off, so make get_boolean the default
            return self.get_boolean(key)
        except:
            # There was setting-specific getter, but it failed.
            return self.settings[key]

    def __getattr__(self, key):
        try:
            return self.settings[key]
        except KeyError:
            raise AttributeError(key)

    def get_boolean(self, key):
        return w.config_string_to_boolean(w.config_get_plugin(key))

    def get_string(self, key):
        return w.config_get_plugin(key)

    def get_int(self, key):
        return int(w.config_get_plugin(key))

    def is_default(self, key):
        default = self.default_settings.get(key).default
        return w.config_get_plugin(key) == default

    get_color_buflist_muted_channels = get_string
    get_color_deleted = get_string
    get_color_edited_suffix = get_string
    get_color_reaction_suffix = get_string
    get_color_reaction_suffix_added_by_you = get_string
    get_color_thread_suffix = get_string
    get_color_typing_notice = get_string
    get_debug_level = get_int
    get_external_user_suffix = get_string
    get_files_download_location = get_string
    get_group_name_prefix = get_string
    get_map_underline_to = get_string
    get_muted_channels_activity = get_string
    get_render_bold_as = get_string
    get_render_italic_as = get_string
    get_shared_name_prefix = get_string
    get_slack_timeout = get_int
    get_unfurl_auto_link_display = get_string

    def get_distracting_channels(self, key):
        return [x.strip() for x in w.config_get_plugin(key).split(',') if x]

    def get_server_aliases(self, key):
        alias_list = w.config_get_plugin(key)
        return dict(item.split(":") for item in alias_list.split(",") if ':' in item)

    def get_slack_api_token(self, key):
        token = w.config_get_plugin("slack_api_token")
        if token.startswith('${sec.data'):
            return w.string_eval_expression(token, {}, {}, {})
        else:
            return token

    def get_render_emoji_as_string(self, key):
        s = w.config_get_plugin(key)
        if s == 'both':
            return s
        return w.config_string_to_boolean(s)

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

        old_thread_color_config = w.config_get_plugin("thread_suffix_color")
        new_thread_color_config = w.config_get_plugin("color_thread_suffix")
        if old_thread_color_config and not new_thread_color_config:
            w.config_set_plugin("color_thread_suffix", old_thread_color_config)


def config_server_buffer_cb(data, key, value):
    for team in EVENTROUTER.teams.values():
        team.buffer_merge(value)
    return w.WEECHAT_RC_OK


# to Trace execution, add `setup_trace()` to startup
# and  to a function and sys.settrace(trace_calls)  to a function
def setup_trace():
    global f
    now = time.time()
    f = open('{}/{}-trace.json'.format(RECORD_DIR, now), 'w')


def trace_calls(frame, event, arg):
    global f
    if event != 'call':
        return
    co = frame.f_code
    func_name = co.co_name
    if func_name == 'write':
        # Ignore write() calls from print statements
        return
    func_line_no = frame.f_lineno
    func_filename = co.co_filename
    caller = frame.f_back
    caller_line_no = caller.f_lineno
    caller_filename = caller.f_code.co_filename
    print('Call to %s on line %s of %s from line %s of %s' % \
        (func_name, func_line_no, func_filename,
         caller_line_no, caller_filename), file=f)
    f.flush()
    return


def initiate_connection(token, retries=3, team=None):
    return SlackRequest(team,
                        'rtm.{}'.format('connect' if team else 'start'),
                        {"batch_presence_aware": 1},
                        retries=retries,
                        token=token,
                        metadata={'initial_connection': True})


if __name__ == "__main__":

    w = WeechatWrapper(weechat)

    if w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE,
                  SCRIPT_DESC, "script_unloaded", ""):

        weechat_version = w.info_get("version_number", "") or 0
        if int(weechat_version) < 0x1030000:
            w.prnt("", "\nERROR: Weechat version 1.3+ is required to use {}.\n\n".format(SCRIPT_NAME))
        else:

            global EVENTROUTER
            EVENTROUTER = EventRouter()

            receive_httprequest_callback = EVENTROUTER.receive_httprequest_callback
            receive_ws_callback = EVENTROUTER.receive_ws_callback

            # Global var section
            slack_debug = None
            config = PluginConfig()
            config_changed_cb = config.config_changed

            typing_timer = time.time()

            hide_distractions = False

            w.hook_config("plugins.var.python." + SCRIPT_NAME + ".*", "config_changed_cb", "")
            w.hook_config("irc.look.server_buffer", "config_server_buffer_cb", "")
            w.hook_modifier("input_text_for_buffer", "input_text_for_buffer_cb", "")

            EMOJI, EMOJI_WITH_SKIN_TONES_REVERSE = load_emoji()
            setup_hooks()

            # attach to the weechat hooks we need

            tokens = [token.strip() for token in config.slack_api_token.split(',')]
            w.prnt('', 'Connecting to {} slack team{}.'
                    .format(len(tokens), '' if len(tokens) == 1 else 's'))
            for t in tokens:
                s = initiate_connection(t)
                EVENTROUTER.receive(s)
            if config.record_events:
                EVENTROUTER.record()
            EVENTROUTER.handle_next()
            # END attach to the weechat hooks we need

            hdata = Hdata(w)

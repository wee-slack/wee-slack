# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from functools import wraps

import time
import json
import pickle
import sha
import os
import re
import urllib
import sys
import traceback
import collections
import ssl
import random
import string

from websocket import create_connection, WebSocketConnectionClosedException

# hack to make tests possible.. better way?
try:
    import weechat
except:
    pass

SCRIPT_NAME = "slack"
SCRIPT_AUTHOR = "Ryan Huber <rhuber@gmail.com>"
SCRIPT_VERSION = "1.99"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Extends weechat for typing notification/search/etc on slack.com"

BACKLOG_SIZE = 200
SCROLLBACK_SIZE = 500

RECORD_DIR = "/tmp/weeslack-debug"

SLACK_API_TRANSLATOR = {
    "channel": {
        "history": "channels.history",
        "join": "channels.join",
        "leave": "channels.leave",
        "mark": "channels.mark",
        "info": "channels.info",
    },
    "im": {
        "history": "im.history",
        "join": "im.open",
        "leave": "im.close",
        "mark": "im.mark",
    },
    "group": {
        "history": "groups.history",
        "join": "channels.join",
        "leave": "groups.leave",
        "mark": "groups.mark",
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
            return w.WEECHAT_RC_ERROR
        return f(data, current_buffer, *args, **kwargs)
    return wrapper


NICK_GROUP_HERE = "0|Here"
NICK_GROUP_AWAY = "1|Away"

sslopt_ca_certs = {}
if hasattr(ssl, "get_default_verify_paths") and callable(ssl.get_default_verify_paths):
    ssl_defaults = ssl.get_default_verify_paths()
    if ssl_defaults.cafile is not None:
        sslopt_ca_certs = {'ca_certs': ssl_defaults.cafile}

###### Unicode handling


def encode_to_utf8(data):
    if isinstance(data, unicode):
        return data.encode('utf-8')
    if isinstance(data, bytes):
        return data
    elif isinstance(data, collections.Mapping):
        return dict(map(encode_to_utf8, data.iteritems()))
    elif isinstance(data, collections.Iterable):
        return type(data)(map(encode_to_utf8, data))
    else:
        return data


def decode_from_utf8(data):
    if isinstance(data, bytes):
        return data.decode('utf-8')
    if isinstance(data, unicode):
        return data
    elif isinstance(data, collections.Mapping):
        return dict(map(decode_from_utf8, data.iteritems()))
    elif isinstance(data, collections.Iterable):
        return type(data)(map(decode_from_utf8, data))
    else:
        return data


class WeechatWrapper(object):
    def __init__(self, wrapped_class):
        self.wrapped_class = wrapped_class

    def __getattr__(self, attr):
        orig_attr = self.wrapped_class.__getattribute__(attr)
        if callable(orig_attr):
            def hooked(*args, **kwargs):
                result = orig_attr(*encode_to_utf8(args), **encode_to_utf8(kwargs))
                # Prevent wrapped_class from becoming unwrapped
                if result == self.wrapped_class:
                    return self
                return decode_from_utf8(result)
            return hooked
        else:
            return decode_from_utf8(orig_attr)


##### BEGIN NEW

IGNORED_EVENTS = [
    "hello",
    # "pref_change",
    # "reconnect_url",
]

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
        self.context = {}
        self.weechat_controller = WeechatController(self)
        self.previous_buffer = ""
        self.reply_buffer = {}
        self.cmds = {k[8:]: v for k, v in globals().items() if k.startswith("command_")}
        self.proc = {k[8:]: v for k, v in globals().items() if k.startswith("process_")}
        self.handlers = {k[7:]: v for k, v in globals().items() if k.startswith("handle_")}
        self.local_proc = {k[14:]: v for k, v in globals().items() if k.startswith("local_process_")}
        self.shutting_down = False
        self.recording = False
        self.recording_path = "/tmp"

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
        data = self.context.get(identifier, None)
        if data:
            # dbg("retrieved context {} ".format(identifier))
            return data

    def delete_context(self, identifier):
        """
        Requests can span multiple requests, so we may need to delete this as a last step
        """
        if identifier in self.context:
            # dbg("deleted eontext {} ".format(identifier))
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
        for team_id, team in self.teams.iteritems():
            if not team.connected:
                team.connect()
                dbg("reconnecting {}".format(team))

    def receive_ws_callback(self, team_hash):
        """
        incomplete (reconnect)
        This is called by the global method of the same name.
        It is triggered when we have incoming data on a websocket,
        which needs to be read. Once it is read, we will ensure
        the data is valid JSON, add metadata, and place it back
        on the queue for processing as JSON.
        """
        try:
            # Read the data from the websocket associated with this team.
            data = decode_from_utf8(self.teams[team_hash].ws.recv())
            message_json = json.loads(data)
            metadata = WeeSlackMetadata({
                "team": team_hash,
            }).jsonify()
            message_json["wee_slack_metadata"] = metadata
            if self.recording:
                self.record_event(message_json, 'type', 'websocket')
            self.receive_json(json.dumps(message_json))
        except WebSocketConnectionClosedException:
            # TODO: handle reconnect here
            self.teams[team_hash].set_disconnected()
            return w.WEECHAT_RC_OK
        except Exception:
            dbg("socket issue: {}\n".format(traceback.format_exc()))
            return w.WEECHAT_RC_OK

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
        try:
            dbg("RECEIVED CALLBACK with request of {} id of {} and  code {} of length {}".format(request_metadata.request, request_metadata.response_id, return_code, len(out)))
        except:
            dbg(request_metadata)
            return
        if return_code == 0:
            if len(out) > 0:
                if request_metadata.response_id in self.reply_buffer:
                    # dbg("found response id in reply_buffer", True)
                    self.reply_buffer[request_metadata.response_id] += out
                else:
                    # dbg("didn't find response id in reply_buffer", True)
                    self.reply_buffer[request_metadata.response_id] = ""
                    self.reply_buffer[request_metadata.response_id] += out
                try:
                    j = json.loads(self.reply_buffer[request_metadata.response_id])
                except:
                    pass
                    # dbg("Incomplete json, awaiting more", True)
                try:
                    j["wee_slack_process_method"] = request_metadata.request_normalized
                    j["wee_slack_request_metadata"] = pickle.dumps(request_metadata)
                    self.reply_buffer.pop(request_metadata.response_id)
                    if self.recording:
                        self.record_event(j, 'wee_slack_process_method', 'http')
                    self.receive_json(json.dumps(j))
                    self.delete_context(data)
                except:
                    dbg("HTTP REQUEST CALLBACK FAILED", True)
                    pass
            # We got an empty reply and this is weird so just ditch it and retry
            else:
                dbg("length was zero, probably a bug..")
                self.delete_context(data)
                self.receive(request_metadata)
        elif return_code != -1:
            self.reply_buffer.pop(request_metadata.response_id, None)
            self.delete_context(data)
        else:
            if request_metadata.response_id not in self.reply_buffer:
                self.reply_buffer[request_metadata.response_id] = ""
            self.reply_buffer[request_metadata.response_id] += out

    def receive_json(self, data):
        """
        complete
        Receives a raw JSON string from and unmarshals it
        as dict, then places it back on the queue for processing.
        """
        dbg("RECEIVED JSON of len {}".format(len(data)))
        message_json = json.loads(data)
        self.queue.append(message_json)

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
        if len(self.slow_queue) > 0 and ((self.slow_queue_timer + 1) < time.time()):
            # for q in self.slow_queue[0]:
            dbg("from slow queue", 0)
            self.queue.append(self.slow_queue.pop())
            # self.slow_queue = []
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

                # Here we are passing the actual objects. No more lookups.
                meta = j.get("wee_slack_metadata", None)
                if meta:
                    try:
                        if isinstance(meta, basestring):
                            dbg("string of metadata")
                        team = meta.get("team", None)
                        if team:
                            kwargs["team"] = self.teams[team]
                            if "user" in j:
                                kwargs["user"] = self.teams[team].users[j["user"]]
                            if "channel" in j:
                                kwargs["channel"] = self.teams[team].channels[j["channel"]]
                    except:
                        dbg("metadata failure")

                if function_name not in IGNORED_EVENTS:
                    dbg("running {}".format(function_name))
                    if function_name.startswith("local_") and function_name in self.local_proc:
                        self.local_proc[function_name](j, self, **kwargs)
                    elif function_name in self.proc:
                        self.proc[function_name](j, self, **kwargs)
                    elif function_name in self.handlers:
                        self.handlers[function_name](j, self, **kwargs)
                    else:
                        raise ProcessNotImplemented(function_name)


def handle_next(*args):
    """
    complete
    This is just a place to call the event router globally.
    This is a dirty hack. There must be a better way.
    """
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
        if isinstance(buffer_ptr, basestring):
            try:
                self.buffers[buffer_ptr].destroy_buffer(update_remote)
                if close_buffer:
                    w.buffer_close(buffer_ptr)
                del self.buffers[buffer_ptr]
            except:
                dbg("Tried to close unknown buffer")
        else:
            raise InvalidType(type(buffer_ptr))

    def get_channel_from_buffer_ptr(self, buffer_ptr):
        return self.buffers.get(buffer_ptr, None)

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


def receive_httprequest_callback(data, command, return_code, out, err):
    """
    complete
    This is a dirty hack. There must be a better way.
    """
    # def url_processor_cb(data, command, return_code, out, err):
    data = decode_from_utf8(data)
    EVENTROUTER.receive_httprequest_callback(data, command, return_code, out, err)
    return w.WEECHAT_RC_OK


def receive_ws_callback(*args):
    """
    complete
    The first arg is all we want here. It contains the team
    hash which is set when we _hook the descriptor.
    This is a dirty hack. There must be a better way.
    """
    EVENTROUTER.receive_ws_callback(args[0])
    return w.WEECHAT_RC_OK


def reconnect_callback(*args):
    EVENTROUTER.reconnect_if_disconnected()
    return w.WEECHAT_RC_OK


def buffer_closing_callback(signal, sig_type, data):
    """
    complete
    Receives a callback from weechat when a buffer is being closed.
    We pass the eventrouter variable name in as a string, as
    that is the only way we can do dependency injection via weechat
    callback, hence the eval.
    """
    data = decode_from_utf8(data)
    eval(signal).weechat_controller.unregister_buffer(data, True, False)
    return w.WEECHAT_RC_OK


def buffer_input_callback(signal, buffer_ptr, data):
    """
    incomplete
    Handles everything a user types in the input bar. In our case
    this includes add/remove reactions, modifying messages, and
    sending messages.
    """
    data = decode_from_utf8(data)
    eventrouter = eval(signal)
    channel = eventrouter.weechat_controller.get_channel_from_buffer_ptr(buffer_ptr)
    if not channel:
        return w.WEECHAT_RC_OK_EAT

    reaction = re.match("^\s*(\d*)(\+|-):(.*):\s*$", data)
    if reaction:
        if reaction.group(2) == "+":
            channel.send_add_reaction(int(reaction.group(1) or 1), reaction.group(3))
        elif reaction.group(2) == "-":
            channel.send_remove_reaction(int(reaction.group(1) or 1), reaction.group(3))
    elif data.startswith('s/'):
        try:
            old, new, flags = re.split(r'(?<!\\)/', data)[1:]
        except ValueError:
            pass
        else:
            # Replacement string in re.sub() is a string, not a regex, so get
            # rid of escapes.
            new = new.replace(r'\/', '/')
            old = old.replace(r'\/', '/')
            channel.edit_previous_message(old, new, flags)
    else:
        channel.send_message(data)
        # this is probably wrong channel.mark_read(update_remote=True, force=True)
    return w.WEECHAT_RC_ERROR


def buffer_switch_callback(signal, sig_type, data):
    """
    incomplete
    Every time we change channels in weechat, we call this to:
    1) set read marker 2) determine if we have already populated
    channel history data
    """
    data = decode_from_utf8(data)
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

    eventrouter.weechat_controller.set_previous_buffer(data)
    return w.WEECHAT_RC_OK


def buffer_list_update_callback(data, somecount):
    """
    incomplete
    A simple timer-based callback that will update the buffer list
    if needed. We only do this max 1x per second, as otherwise it
    uses a lot of cpu for minimal changes. We use buffer short names
    to indicate typing via "#channel" <-> ">channel" and
    user presence via " name" <-> "+name".
    """
    data = decode_from_utf8(data)
    eventrouter = eval(data)
    # global buffer_list_update

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


def typing_notification_cb(signal, sig_type, data):
    data = decode_from_utf8(data)
    msg = w.buffer_get_string(data, "input")
    if len(msg) > 8 and msg[:1] != "/":
        global typing_timer
        now = time.time()
        if typing_timer + 4 < now:
            current_buffer = w.current_buffer()
            channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer, None)
            if channel:
                identifier = channel.identifier
                request = {"type": "typing", "channel": identifier}
                channel.team.send_to_websocket(request, expect_reply=False)
                typing_timer = now
    return w.WEECHAT_RC_OK


def typing_update_cb(data, remaining_calls):
    data = decode_from_utf8(data)
    w.bar_item_update("slack_typing_notice")
    return w.WEECHAT_RC_OK


def slack_never_away_cb(data, remaining_calls):
    data = decode_from_utf8(data)
    if config.never_away:
        for t in EVENTROUTER.teams.values():
            slackbot = t.get_channel_map()['slackbot']
            channel = t.channels[slackbot]
            request = {"type": "typing", "channel": channel.identifier}
            channel.team.send_to_websocket(request, expect_reply=False)
    return w.WEECHAT_RC_OK


def typing_bar_item_cb(data, current_buffer, args):
    """
    Privides a bar item indicating who is typing in the current channel AND
    why is typing a DM to you globally.
    """
    typers = []
    current_buffer = w.current_buffer()
    current_channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer, None)

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
    for t in EVENTROUTER.teams.values():
        for channel in t.channels.values():
            if channel.type == "im":
                if channel.is_someone_typing():
                    typers.append("D/" + channel.slack_name)
                pass

    typing = ", ".join(typers)
    if typing != "":
        typing = w.color('yellow') + "typing: " + typing

    return typing


def nick_completion_cb(data, completion_item, current_buffer, completion):
    """
    Adds all @-prefixed nicks to completion list
    """

    data = decode_from_utf8(data)
    completion = decode_from_utf8(completion)
    current_buffer = w.current_buffer()
    current_channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer, None)

    if current_channel is None or current_channel.members is None:
        return w.WEECHAT_RC_OK
    for m in current_channel.members:
        u = current_channel.team.users.get(m, None)
        if u:
            w.hook_completion_list_add(completion, "@" + u.slack_name, 1, w.WEECHAT_LIST_POS_SORT)
    return w.WEECHAT_RC_OK


def emoji_completion_cb(data, completion_item, current_buffer, completion):
    """
    Adds all :-prefixed emoji to completion list
    """

    data = decode_from_utf8(data)
    completion = decode_from_utf8(completion)
    current_buffer = w.current_buffer()
    current_channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer, None)

    if current_channel is None:
        return w.WEECHAT_RC_OK
    for e in EMOJI['emoji']:
        w.hook_completion_list_add(completion, ":" + e + ":", 0, w.WEECHAT_LIST_POS_SORT)
    return w.WEECHAT_RC_OK


def complete_next_cb(data, current_buffer, command):
    """Extract current word, if it is equal to a nick, prefix it with @ and
    rely on nick_completion_cb adding the @-prefixed versions to the
    completion lists, then let Weechat's internal completion do its
    thing

    """

    data = decode_from_utf8(data)
    command = decode_from_utf8(data)
    current_buffer = w.current_buffer()
    current_channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer, None)

    # channel = channels.find(current_buffer)
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

    for m in current_channel.members:
        u = current_channel.team.users.get(m, None)
        if u and u.slack_name == word:
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
    return w.WEECHAT_RC_OK

##### New Classes


class SlackRequest(object):
    """
    complete
    Encapsulates a Slack api request. Valuable as an object that we can add to the queue and/or retry.
    makes a SHA of the requst url and current time so we can re-tag this on the way back through.
    """

    def __init__(self, token, request, post_data={}, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.tries = 0
        self.start_time = time.time()
        self.domain = 'api.slack.com'
        self.request = request
        self.request_normalized = re.sub(r'\W+', '', request)
        self.token = token
        post_data["token"] = token
        self.post_data = post_data
        self.params = {'useragent': 'wee_slack {}'.format(SCRIPT_VERSION)}
        self.url = 'https://{}/api/{}?{}'.format(self.domain, request, urllib.urlencode(encode_to_utf8(post_data)))
        self.response_id = sha.sha("{}{}".format(self.url, self.start_time)).hexdigest()
        self.retries = kwargs.get('retries', 3)
#    def __repr__(self):
#        return "URL: {} Tries: {} ID: {}".format(self.url, self.tries, self.response_id)

    def request_string(self):
        return "{}".format(self.url)

    def tried(self):
        self.tries += 1
        self.response_id = sha.sha("{}{}".format(self.url, time.time())).hexdigest()

    def should_try(self):
        return self.tries < self.retries

    def retry_ready(self):
        return (self.start_time + (self.tries**2)) < time.time()


class SlackTeam(object):
    """
    incomplete
    Team object under which users and channels live.. Does lots.
    """

    def __init__(self, eventrouter, token, websocket_url, subdomain, nick, myidentifier, users, bots, channels, **kwargs):
        self.ws_url = websocket_url
        self.connected = False
        self.connecting = False
        # self.ws = None
        self.ws_counter = 0
        self.ws_replies = {}
        self.eventrouter = eventrouter
        self.token = token
        self.team = self
        self.subdomain = subdomain
        self.domain = subdomain + ".slack.com"
        self.preferred_name = self.domain
        self.nick = nick
        self.myidentifier = myidentifier
        try:
            if self.channels:
                for c in channels.keys():
                    if not self.channels.get(c):
                        self.channels[c] = channels[c]
        except:
            self.channels = channels
        self.users = users
        self.bots = bots
        self.team_hash = SlackTeam.generate_team_hash(self.nick, self.subdomain)
        self.name = self.domain
        self.channel_buffer = None
        self.got_history = True
        self.create_buffer()
        self.set_muted_channels(kwargs.get('muted_channels', ""))
        for c in self.channels.keys():
            channels[c].set_related_server(self)
            channels[c].check_should_open()
        #    self.channel_set_related_server(c)
        # Last step is to make sure my nickname is the set color
        self.users[self.myidentifier].force_color(w.config_string(w.config_get('weechat.color.chat_nick_self')))
        # This highlight step must happen after we have set related server
        self.set_highlight_words(kwargs.get('highlight_words', ""))

    def __eq__(self, compare_str):
        if compare_str == self.token or compare_str == self.domain or compare_str == self.subdomain:
            return True
        else:
            return False

    def add_channel(self, channel):
        self.channels[channel["id"]] = channel
        channel.set_related_server(self)

    # def connect_request_generate(self):
    #    return SlackRequest(self.token, 'rtm.start', {})

    # def close_all_buffers(self):
    #    for channel in self.channels:
    #        self.eventrouter.weechat_controller.unregister_buffer(channel.channel_buffer, update_remote=False, close_buffer=True)
    #    #also close this server buffer
    #    self.eventrouter.weechat_controller.unregister_buffer(self.channel_buffer, update_remote=False, close_buffer=True)

    def create_buffer(self):
        if not self.channel_buffer:
            if config.short_buffer_names:
                self.preferred_name = self.subdomain
            elif config.server_aliases not in ['', None]:
                name = config.server_aliases.get(self.subdomain, None)
                if name:
                    self.preferred_name = name
            else:
                self.preferred_name = self.domain
            self.channel_buffer = w.buffer_new("{}".format(self.preferred_name), "buffer_input_callback", "EVENTROUTER", "", "")
            self.eventrouter.weechat_controller.register_buffer(self.channel_buffer, self)
            w.buffer_set(self.channel_buffer, "localvar_set_type", 'server')
            if w.config_string(w.config_get('irc.look.server_buffer')) == 'merge_with_core':
                w.buffer_merge(self.channel_buffer, w.buffer_search_main())
            w.buffer_set(self.channel_buffer, "nicklist", "1")

    def set_muted_channels(self, muted_str):
        self.muted_channels = {x for x in muted_str.split(',')}

    def set_highlight_words(self, highlight_str):
        self.highlight_words = {x for x in highlight_str.split(',')}
        if len(self.highlight_words) > 0:
            for v in self.channels.itervalues():
                v.set_highlights()

    def formatted_name(self, **kwargs):
        return self.domain

    def buffer_prnt(self, data):
        w.prnt_date_tags(self.channel_buffer, SlackTS().major, tag("backlog"), data)

    def get_channel_map(self):
        return {v.slack_name: k for k, v in self.channels.iteritems()}

    def get_username_map(self):
        return {v.slack_name: k for k, v in self.users.iteritems()}

    def get_team_hash(self):
        return self.team_hash

    @staticmethod
    def generate_team_hash(nick, subdomain):
        return str(sha.sha("{}{}".format(nick, subdomain)).hexdigest())

    def refresh(self):
        self.rename()

    def rename(self):
        pass

    # def attach_websocket(self, ws):
    #    self.ws = ws

    def is_user_present(self, user_id):
        user = self.users.get(user_id)
        if user.presence == 'active':
            return True
        else:
            return False

    def mark_read(self):
        pass

    def connect(self):
        if not self.connected and not self.connecting:
            self.connecting = True
            if self.ws_url:
                try:
                    ws = create_connection(self.ws_url, sslopt=sslopt_ca_certs)
                    w.hook_fd(ws.sock._sock.fileno(), 1, 0, 0, "receive_ws_callback", self.get_team_hash())
                    ws.sock.setblocking(0)
                    self.ws = ws
                    # self.attach_websocket(ws)
                    self.set_connected()
                    self.connecting = False
                except Exception as e:
                    dbg("websocket connection error: {}".format(e))
                    self.connecting = False
                    return False
            else:
                # The fast reconnect failed, so start over-ish
                for chan in self.channels:
                    self.channels[chan].got_history = False
                s = SlackRequest(self.token, 'rtm.start', {}, retries=999)
                self.eventrouter.receive(s)
                self.connecting = False
                # del self.eventrouter.teams[self.get_team_hash()]
            self.set_reconnect_url(None)

    def set_connected(self):
        self.connected = True

    def set_disconnected(self):
        self.connected = False

    def set_reconnect_url(self, url):
        self.ws_url = url

    def next_ws_transaction_id(self):
        if self.ws_counter > 999:
            self.ws_counter = 0
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
        except:
            print "WS ERROR"
            dbg("Unexpected error: {}\nSent: {}".format(sys.exc_info()[0], data))
            self.set_connected()


class SlackChannel(object):
    """
    Represents an individual slack channel.
    """

    def __init__(self, eventrouter, **kwargs):
        # We require these two things for a vaid object,
        # the rest we can just learn from slack
        self.active = False
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.members = set(kwargs.get('members', set()))
        self.eventrouter = eventrouter
        self.slack_name = kwargs["name"]
        self.slack_topic = kwargs.get("topic", {"value": ""})
        self.slack_purpose = kwargs.get("purpose", {"value": ""})
        self.identifier = kwargs["id"]
        self.last_read = SlackTS(kwargs.get("last_read", SlackTS()))
        self.channel_buffer = None
        self.team = kwargs.get('team', None)
        self.got_history = False
        self.messages = {}
        self.hashed_messages = {}
        self.new_messages = False
        self.typing = {}
        self.type = 'channel'
        self.set_name(self.slack_name)
        # short name relates to the localvar we change for typing indication
        self.current_short_name = self.name
        self.update_nicklist()

    def __eq__(self, compare_str):
        if compare_str == self.slack_name or compare_str == self.formatted_name() or compare_str == self.formatted_name(style="long_default"):
            return True
        else:
            return False

    def __repr__(self):
        return "Name:{} Identifier:{}".format(self.name, self.identifier)

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

    def formatted_name(self, style="default", typing=False, **kwargs):
        if config.channel_name_typing_indicator:
            if not typing:
                prepend = "#"
            else:
                prepend = ">"
        else:
            prepend = "#"
        select = {
            "default": prepend + self.slack_name,
            "sidebar": prepend + self.slack_name,
            "base": self.slack_name,
            "long_default": "{}.{}{}".format(self.team.preferred_name, prepend, self.slack_name),
            "long_base": "{}.{}".format(self.team.preferred_name, self.slack_name),
        }
        return select[style]

    def render_topic(self, topic=None):
        if self.channel_buffer:
            if not topic:
                if self.slack_topic['value'] != "":
                    topic = self.slack_topic['value']
                else:
                    topic = self.slack_purpose['value']
            w.buffer_set(self.channel_buffer, "title", topic)

    def update_from_message_json(self, message_json):
        for key, value in message_json.items():
            setattr(self, key, value)

    def open(self, update_remote=True):
        if update_remote:
            if "join" in SLACK_API_TRANSLATOR[self.type]:
                s = SlackRequest(self.team.token, SLACK_API_TRANSLATOR[self.type]["join"], {"name": self.name}, team_hash=self.team.team_hash, channel_identifier=self.identifier)
                self.eventrouter.receive(s)
        self.create_buffer()
        self.active = True
        self.get_history()
        if "info" in SLACK_API_TRANSLATOR[self.type]:
            s = SlackRequest(self.team.token, SLACK_API_TRANSLATOR[self.type]["info"], {"name": self.identifier}, team_hash=self.team.team_hash, channel_identifier=self.identifier)
            self.eventrouter.receive(s)
        # self.create_buffer()

    def check_should_open(self, force=False):
        try:
            if self.is_archived:
                return
        except:
            pass
        if force:
            self.create_buffer()
        else:
            for reason in ["is_member", "is_open", "unread_count_display"]:
                try:
                    if eval("self." + reason):
                        self.create_buffer()
                        if config.background_load_all_history:
                            self.get_history(slow_queue=True)
                except:
                    pass

    def set_related_server(self, team):
        self.team = team

    def set_highlights(self):
        # highlight my own name and any set highlights
        if self.channel_buffer:
            highlights = self.team.highlight_words.union({'@' + self.team.nick, "!here", "!channel", "!everyone"})
            h_str = ",".join(highlights)
            w.buffer_set(self.channel_buffer, "highlight_words", h_str)

    def create_buffer(self):
        """
        incomplete (muted doesn't work)
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
            w.buffer_set(self.channel_buffer, "short_name", self.formatted_name(style="sidebar", enable_color=True))
            self.render_topic()
            self.eventrouter.weechat_controller.set_refresh_buffer_list(True)
            if self.channel_buffer:
                # if self.team.server_alias:
                #    w.buffer_set(self.channel_buffer, "localvar_set_server", self.team.server_alias)
                # else:
                w.buffer_set(self.channel_buffer, "localvar_set_server", self.team.preferred_name)
        # else:
        #    self.eventrouter.weechat_controller.register_buffer(self.channel_buffer, self)
            try:
                for c in range(self.unread_count_display):
                    if self.type == "im":
                        w.buffer_set(self.channel_buffer, "hotlist", "2")
                    else:
                        w.buffer_set(self.channel_buffer, "hotlist", "1")
                else:
                    pass
                    # dbg("no unread in {}".format(self.name))
            except:
                pass

        self.update_nicklist()
        # dbg("exception no unread count")
        # if self.unread_count != 0 and not self.muted:
        #    w.buffer_set(self.channel_buffer, "hotlist", "1")

    def destroy_buffer(self, update_remote):
        if self.channel_buffer is not None:
            self.channel_buffer = None
        self.messages = {}
        self.hashed_messages = {}
        self.got_history = False
        # if update_remote and not eventrouter.shutting_down:
        self.active = False
        if update_remote and not self.eventrouter.shutting_down:
            s = SlackRequest(self.team.token, SLACK_API_TRANSLATOR[self.type]["leave"], {"channel": self.identifier}, team_hash=self.team.team_hash, channel_identifier=self.identifier)
            self.eventrouter.receive(s)

    def buffer_prnt(self, nick, text, timestamp=str(time.time()), tagset=None, tag_nick=None, **kwargs):
        data = "{}\t{}".format(nick, text)
        ts = SlackTS(timestamp)
        last_read = SlackTS(self.last_read)
        # without this, DMs won't open automatically
        if not self.channel_buffer and ts > last_read:
            self.open(update_remote=False)
        if self.channel_buffer:
            # backlog messages - we will update the read marker as we print these
            backlog = True if ts <= last_read else False
            if tagset:
                tags = tag(tagset, user=tag_nick)
                self.new_messages = True

            # we have to infer the tagset because we weren't told
            elif ts <= last_read:
                tags = tag("backlog", user=tag_nick)
            elif self.type in ["im", "mpdm"]:
                if nick != self.team.nick:
                    tags = tag("dm", user=tag_nick)
                    self.new_messages = True
                else:
                    tags = tag("dmfromme")
            else:
                tags = tag("default", user=tag_nick)
                self.new_messages = True

            try:
                if config.unhide_buffers_with_activity and not self.is_visible() and (self.identifier not in self.team.muted_channels):
                    w.buffer_set(self.channel_buffer, "hidden", "0")

                w.prnt_date_tags(self.channel_buffer, ts.major, tags, data)
                modify_print_time(self.channel_buffer, ts.minorstr(), ts.major)
                if backlog:
                    self.mark_read(ts, update_remote=False, force=True)
            except:
                dbg("Problem processing buffer_prnt")

    def send_message(self, message, request_dict_ext={}):
        # team = self.eventrouter.teams[self.team]
        message = linkify_text(message, self.team, self)
        dbg(message)
        request = {"type": "message", "channel": self.identifier, "text": message, "_team": self.team.team_hash, "user": self.team.myidentifier}
        request.update(request_dict_ext)
        self.team.send_to_websocket(request)
        self.mark_read(update_remote=False, force=True)

    def store_message(self, message, team, from_me=False):
        if not self.active:
            return
        if from_me:
            message.message_json["user"] = team.myidentifier
        self.messages[SlackTS(message.ts)] = message
        if len(self.messages.keys()) > SCROLLBACK_SIZE:
            mk = self.messages.keys()
            mk.sort()
            for k in mk[:SCROLLBACK_SIZE]:
                msg_to_delete = self.messages[k]
                if msg_to_delete.hash:
                    del self.hashed_messages[msg_to_delete.hash]
                del self.messages[k]

    def change_message(self, ts, text=None, suffix=None):
        ts = SlackTS(ts)
        if ts in self.messages:
            m = self.messages[ts]
            if text:
                m.change_text(text)
            if suffix:
                m.change_suffix(suffix)
            text = m.render(force=True)
        modify_buffer_line(self.channel_buffer, text, ts.major, ts.minor)
        return True

    def edit_previous_message(self, old, new, flags):
        message = self.my_last_message()
        if new == "" and old == "":
            s = SlackRequest(self.team.token, "chat.delete", {"channel": self.identifier, "ts": message['ts']}, team_hash=self.team.team_hash, channel_identifier=self.identifier)
            self.eventrouter.receive(s)
        else:
            num_replace = 1
            if 'g' in flags:
                num_replace = 0
            new_message = re.sub(old, new, message["text"], num_replace)
            if new_message != message["text"]:
                s = SlackRequest(self.team.token, "chat.update", {"channel": self.identifier, "ts": message['ts'], "text": new_message}, team_hash=self.team.team_hash, channel_identifier=self.identifier)
                self.eventrouter.receive(s)

    def my_last_message(self):
        for message in reversed(self.sorted_message_keys()):
            m = self.messages[message]
            if "user" in m.message_json and "text" in m.message_json and m.message_json["user"] == self.team.myidentifier:
                return m.message_json

    def is_visible(self):
        return w.buffer_get_integer(self.channel_buffer, "hidden") == 0

    def get_history(self, slow_queue=False):
        if not self.got_history:
            # we have probably reconnected. flush the buffer
            if self.team.connected:
                w.buffer_clear(self.channel_buffer)
            self.buffer_prnt('', 'getting channel history...', tagset='backlog')
            s = SlackRequest(self.team.token, SLACK_API_TRANSLATOR[self.type]["history"], {"channel": self.identifier, "count": BACKLOG_SIZE}, team_hash=self.team.team_hash, channel_identifier=self.identifier, clear=True)
            if not slow_queue:
                self.eventrouter.receive(s)
            else:
                self.eventrouter.receive_slow(s)
            self.got_history = True

    def send_add_reaction(self, msg_number, reaction):
        self.send_change_reaction("reactions.add", msg_number, reaction)

    def send_remove_reaction(self, msg_number, reaction):
        self.send_change_reaction("reactions.remove", msg_number, reaction)

    def send_change_reaction(self, method, msg_number, reaction):
        if 0 < msg_number < len(self.messages):
            timestamp = self.sorted_message_keys()[-msg_number]
            data = {"channel": self.identifier, "timestamp": timestamp, "name": reaction}
            s = SlackRequest(self.team.token, method, data)
            self.eventrouter.receive(s)

    def sorted_message_keys(self):
        keys = []
        for k in self.messages:
            if type(self.messages[k]) == SlackMessage:
                keys.append(k)
        return sorted(keys)

    # Typing related
    def set_typing(self, user):
        if self.channel_buffer and self.is_visible():
            self.typing[user] = time.time()
            self.eventrouter.weechat_controller.set_refresh_buffer_list(True)

    def unset_typing(self, user):
        if self.channel_buffer and self.is_visible():
            u = self.typing.get(user, None)
            if u:
                self.eventrouter.weechat_controller.set_refresh_buffer_list(True)

    def is_someone_typing(self):
        """
        Walks through dict of typing folks in a channel and fast
        returns if any of them is actively typing. If none are,
        nulls the dict and returns false.
        """
        for user, timestamp in self.typing.iteritems():
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
        for user, timestamp in self.typing.iteritems():
            if timestamp + 4 > time.time():
                typing.append(user)
            else:
                del self.typing[user]
        return typing

    def mark_read(self, ts=None, update_remote=True, force=False):
        if not ts:
            ts = SlackTS()
        if self.new_messages or force:
            if self.channel_buffer:
                w.buffer_set(self.channel_buffer, "unread", "")
                w.buffer_set(self.channel_buffer, "hotlist", "-1")
            if update_remote:
                s = SlackRequest(self.team.token, SLACK_API_TRANSLATOR[self.type]["mark"], {"channel": self.identifier, "ts": ts}, team_hash=self.team.team_hash, channel_identifier=self.identifier)
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
        if self.type not in ["channel", "group"]:
            return
        w.buffer_set(self.channel_buffer, "nicklist", "1")
        # create nicklists for the current channel if they don't exist
        # if they do, use the existing pointer
        # TODO: put this back for mithrandir
        # here = w.nicklist_search_group(self.channel_buffer, '', NICK_GROUP_HERE)
        # if not here:
        #    here = w.nicklist_add_group(self.channel_buffer, '', NICK_GROUP_HERE, "weechat.color.nicklist_group", 1)
        # afk = w.nicklist_search_group(self.channel_buffer, '', NICK_GROUP_AWAY)
        # if not afk:
        #    afk = w.nicklist_add_group(self.channel_buffer, '', NICK_GROUP_AWAY, "weechat.color.nicklist_group", 1)

        if user and len(self.members) < 1000:
            user = self.team.users[user]
            nick = w.nicklist_search_nick(self.channel_buffer, "", user.slack_name)
            # since this is a change just remove it regardless of where it is
            w.nicklist_remove_nick(self.channel_buffer, nick)
            # now add it back in to whichever..
            if user.identifier in self.members:
                w.nicklist_add_nick(self.channel_buffer, "", user.name, user.color_name, "", "", 1)
            # w.nicklist_add_nick(self.channel_buffer, here, user.name, user.color_name, "", "", 1)

        # if we didn't get a user, build a complete list. this is expensive.
        else:
            if len(self.members) < 1000:
                try:
                    for user in self.members:
                        user = self.team.users[user]
                        if user.deleted:
                            continue
                        w.nicklist_add_nick(self.channel_buffer, "", user.name, user.color_name, "", "", 1)
                        # w.nicklist_add_nick(self.channel_buffer, here, user.name, user.color_name, "", "", 1)
                except Exception as e:
                    dbg("DEBUG: {} {} {}".format(self.identifier, self.name, e))
            else:
                for fn in ["1| too", "2| many", "3| users", "4| to", "5| show"]:
                    w.nicklist_add_group(self.channel_buffer, '', fn, w.color('white'), 1)

    def hash_message(self, ts):
        ts = SlackTS(ts)

        def calc_hash(msg):
            return sha.sha(str(msg.ts)).hexdigest()

        if ts in self.messages and not self.messages[ts].hash:
            message = self.messages[ts]
            tshash = calc_hash(message)
            hl = 3
            shorthash = tshash[:hl]
            while any(x.startswith(shorthash) for x in self.hashed_messages):
                hl += 1
                shorthash = tshash[:hl]

            if shorthash[:-1] in self.hashed_messages:
                col_msg = self.hashed_messages.pop(shorthash[:-1])
                col_new_hash = calc_hash(col_msg)[:hl]
                col_msg.hash = col_new_hash
                self.hashed_messages[col_new_hash] = col_msg
                self.change_message(str(col_msg.ts))
                if col_msg.thread_channel:
                    col_msg.thread_channel.rename()

            self.hashed_messages[shorthash] = message
            message.hash = shorthash


class SlackDMChannel(SlackChannel):
    """
    Subclass of a normal channel for person-to-person communication, which
    has some important differences.
    """

    def __init__(self, eventrouter, users, **kwargs):
        dmuser = kwargs["user"]
        kwargs["name"] = users[dmuser].name
        super(SlackDMChannel, self).__init__(eventrouter, **kwargs)
        self.type = 'im'
        self.update_color()
        self.set_name(self.slack_name)

    def set_name(self, slack_name):
        self.name = slack_name

    def create_buffer(self):
        if not self.channel_buffer:
            super(SlackDMChannel, self).create_buffer()
            w.buffer_set(self.channel_buffer, "localvar_set_type", 'private')

    def update_color(self):
        if config.colorize_private_chats:
            self.color_name = w.info_get('irc_nick_color_name', self.name)
            self.color = w.color(self.color_name)
        else:
            self.color = ""
            self.color_name = ""

    def formatted_name(self, style="default", typing=False, present=True, enable_color=False, **kwargs):
        if config.colorize_private_chats and enable_color:
            print_color = self.color
        else:
            print_color = ""
        if not present:
            prepend = " "
        else:
            prepend = "+"
        select = {
            "default": self.slack_name,
            "sidebar": prepend + self.slack_name,
            "base": self.slack_name,
            "long_default": "{}.{}".format(self.team.preferred_name, self.slack_name),
            "long_base": "{}.{}".format(self.team.preferred_name, self.slack_name),
        }
        return print_color + select[style]

    def open(self, update_remote=True):
        self.create_buffer()
        # self.active = True
        self.get_history()
        if "info" in SLACK_API_TRANSLATOR[self.type]:
            s = SlackRequest(self.team.token, SLACK_API_TRANSLATOR[self.type]["info"], {"name": self.identifier}, team_hash=self.team.team_hash, channel_identifier=self.identifier)
            self.eventrouter.receive(s)
        if update_remote:
            if "join" in SLACK_API_TRANSLATOR[self.type]:
                s = SlackRequest(self.team.token, SLACK_API_TRANSLATOR[self.type]["join"], {"user": self.user}, team_hash=self.team.team_hash, channel_identifier=self.identifier)
                self.eventrouter.receive(s)
        self.create_buffer()

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
        self.name = "#" + kwargs['name']
        self.type = "group"
        self.set_name(self.slack_name)

    def set_name(self, slack_name):
        self.name = "#" + slack_name

    # def formatted_name(self, prepend="#", enable_color=True, basic=False):
    #    return prepend + self.slack_name


class SlackMPDMChannel(SlackChannel):
    """
    An MPDM channel is a special instance of a 'group' channel.
    We change the name to look less terrible in weechat.
    """

    def __init__(self, eventrouter, **kwargs):
        super(SlackMPDMChannel, self).__init__(eventrouter, **kwargs)
        n = kwargs.get('name')
        self.set_name(n)
        self.type = "group"

    def open(self, update_remote=False):
        self.create_buffer()
        self.active = True
        self.get_history()
        if "info" in SLACK_API_TRANSLATOR[self.type]:
            s = SlackRequest(self.team.token, SLACK_API_TRANSLATOR[self.type]["info"], {"name": self.identifier}, team_hash=self.team.team_hash, channel_identifier=self.identifier)
            self.eventrouter.receive(s)
        # self.create_buffer()

    def set_name(self, n):
        self.name = "|".join("-".join(n.split("-")[1:-1]).split("--"))

    def formatted_name(self, style="default", typing=False, **kwargs):
        adjusted_name = "|".join("-".join(self.slack_name.split("-")[1:-1]).split("--"))
        if config.channel_name_typing_indicator:
            if not typing:
                prepend = "#"
            else:
                prepend = ">"
        else:
            prepend = "#"
        select = {
            "default": adjusted_name,
            "sidebar": prepend + adjusted_name,
            "base": adjusted_name,
            "long_default": "{}.{}".format(self.team.preferred_name, adjusted_name),
            "long_base": "{}.{}".format(self.team.preferred_name, adjusted_name),
        }
        return select[style]

    def rename(self):
        pass


class SlackThreadChannel(object):
    """
    A thread channel is a virtual channel. We don't inherit from
    SlackChannel, because most of how it operates will be different.
    """

    def __init__(self, eventrouter, parent_message):
        self.eventrouter = eventrouter
        self.parent_message = parent_message
        self.channel_buffer = None
        # self.identifier = ""
        # self.name = "#" + kwargs['name']
        self.type = "thread"
        self.got_history = False
        self.label = None
        # self.set_name(self.slack_name)
    # def set_name(self, slack_name):
    #    self.name = "#" + slack_name

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

    def buffer_prnt(self, nick, text, timestamp, **kwargs):
        data = "{}\t{}".format(nick, text)
        ts = SlackTS(timestamp)
        if self.channel_buffer:
            # backlog messages - we will update the read marker as we print these
            # backlog = False
            # if ts <= SlackTS(self.last_read):
            #    tags = tag("backlog")
            #    backlog = True
            # elif self.type in ["im", "mpdm"]:
            #    tags = tag("dm")
            #    self.new_messages = True
            # else:
            tags = tag("default")
            # self.new_messages = True
            w.prnt_date_tags(self.channel_buffer, ts.major, tags, data)
            modify_print_time(self.channel_buffer, ts.minorstr(), ts.major)
            # if backlog:
            #    self.mark_read(ts, update_remote=False, force=True)

    def get_history(self):
        self.got_history = True
        for message in self.parent_message.submessages:

            # message = SlackMessage(message_json, team, channel)
            text = message.render()
            # print text

            suffix = ''
            if 'edited' in message.message_json:
                suffix = ' (edited)'
            # try:
            #    channel.unread_count += 1
            # except:
            #    channel.unread_count = 1
            self.buffer_prnt(message.sender, text + suffix, message.ts)

    def send_message(self, message):
        # team = self.eventrouter.teams[self.team]
        message = linkify_text(message, self.parent_message.team, self)
        dbg(message)
        request = {"type": "message", "channel": self.parent_message.channel.identifier, "text": message, "_team": self.parent_message.team.team_hash, "user": self.parent_message.team.myidentifier, "thread_ts": str(self.parent_message.ts)}
        self.parent_message.team.send_to_websocket(request)
        self.mark_read(update_remote=False, force=True)

    def open(self, update_remote=True):
        self.create_buffer()
        self.active = True
        self.get_history()
        # if "info" in SLACK_API_TRANSLATOR[self.type]:
        #    s = SlackRequest(self.team.token, SLACK_API_TRANSLATOR[self.type]["info"], {"name": self.identifier}, team_hash=self.team.team_hash, channel_identifier=self.identifier)
        #    self.eventrouter.receive(s)
        # if update_remote:
        #    if "join" in SLACK_API_TRANSLATOR[self.type]:
        #        s = SlackRequest(self.team.token, SLACK_API_TRANSLATOR[self.type]["join"], {"name": self.name}, team_hash=self.team.team_hash, channel_identifier=self.identifier)
        #        self.eventrouter.receive(s)
        self.create_buffer()

    def rename(self):
        if self.channel_buffer and not self.label:
            w.buffer_set(self.channel_buffer, "short_name", self.formatted_name(style="sidebar", enable_color=True))

    def create_buffer(self):
        """
        incomplete (muted doesn't work)
        Creates the weechat buffer where the thread magic happens.
        """
        if not self.channel_buffer:
            self.channel_buffer = w.buffer_new(self.formatted_name(style="long_default"), "buffer_input_callback", "EVENTROUTER", "", "")
            self.eventrouter.weechat_controller.register_buffer(self.channel_buffer, self)
            w.buffer_set(self.channel_buffer, "localvar_set_type", 'channel')
            w.buffer_set(self.channel_buffer, "localvar_set_channel", self.formatted_name())
            w.buffer_set(self.channel_buffer, "short_name", self.formatted_name(style="sidebar", enable_color=True))
            time_format = w.config_string(w.config_get("weechat.look.buffer_time_format"))
            parent_time = time.localtime(SlackTS(self.parent_message.ts).major)
            topic = '{} {} | {}'.format(time.strftime(time_format, parent_time), self.parent_message.sender, self.parent_message.render()	)
            w.buffer_set(self.channel_buffer, "title", topic)

            # self.eventrouter.weechat_controller.set_refresh_buffer_list(True)

        # try:
        #    if self.unread_count != 0:
        #        for c in range(1, self.unread_count):
        #            if self.type == "im":
        #                w.buffer_set(self.channel_buffer, "hotlist", "2")
        #            else:
        #                w.buffer_set(self.channel_buffer, "hotlist", "1")
        #    else:
        #        pass
        #        #dbg("no unread in {}".format(self.name))
        # except:
        #    pass
        #    dbg("exception no unread count")
        # if self.unread_count != 0 and not self.muted:
        #    w.buffer_set(self.channel_buffer, "hotlist", "1")

    def destroy_buffer(self, update_remote):
        if self.channel_buffer is not None:
            self.channel_buffer = None
        self.got_history = False
        # if update_remote and not eventrouter.shutting_down:
        self.active = False


class SlackUser(object):
    """
    Represends an individual slack user. Also where you set their name formatting.
    """

    def __init__(self, **kwargs):
        # We require these two things for a vaid object,
        # the rest we can just learn from slack
        self.identifier = kwargs["id"]
        self.slack_name = kwargs["name"]
        self.name = kwargs["name"]
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.update_color()

    def __repr__(self):
        return "Name:{} Identifier:{}".format(self.name, self.identifier)

    def force_color(self, color_name):
        self.color_name = color_name
        self.color = w.color(self.color_name)

    def update_color(self):
        # This will automatically be none/"" if the user has disabled nick
        # colourization.
        self.color_name = w.info_get('nick_color_name', self.name)
        self.color = w.color(self.color_name)

    def formatted_name(self, prepend="", enable_color=True):
        if enable_color:
            return self.color + prepend + self.name
        else:
            return prepend + self.name


class SlackBot(SlackUser):
    """
    Basically the same as a user, but split out to identify and for future
    needs
    """
    def __init__(self, **kwargs):
        super(SlackBot, self).__init__(**kwargs)


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
        self.thread_channel = None
        self.hash = None
        if override_sender:
            self.sender = override_sender
            self.sender_plain = override_sender
        else:
            senders = self.get_sender()
            self.sender, self.sender_plain = senders[0], senders[1]
        self.suffix = ''
        self.ts = SlackTS(message_json['ts'])
        text = self.message_json.get('text')
        if text and text.startswith('_') and text.endswith('_') and 'subtype' not in message_json:
            message_json['text'] = text[1:-1]
            message_json['subtype'] = 'me_message'
        if message_json.get('subtype') == 'me_message' and not message_json['text'].startswith(self.sender):
            message_json['text'] = self.sender + ' ' + self.message_json['text']

    def __hash__(self):
        return hash(self.ts)

    def render(self, force=False):
        if len(self.submessages) > 0:
            return "{} {} {}".format(render(self.message_json, self.team, self.channel, force), self.suffix, "{}[ Thread: {} Replies: {} ]".format(w.color(config.thread_suffix_color), self.hash or self.ts, len(self.submessages)))
        return "{} {}".format(render(self.message_json, self.team, self.channel, force), self.suffix)

    def change_text(self, new_text):
        self.message_json["text"] = new_text
        dbg(self.message_json)

    def change_suffix(self, new_suffix):
        self.suffix = new_suffix
        dbg(self.message_json)

    def get_sender(self):
        name = ""
        name_plain = ""
        if 'bot_id' in self.message_json and self.message_json['bot_id'] is not None:
            name = "{} :]".format(self.team.bots[self.message_json["bot_id"]].formatted_name())
            name_plain = "{}".format(self.team.bots[self.message_json["bot_id"]].formatted_name(enable_color=False))
        elif 'user' in self.message_json:
            if self.message_json['user'] == self.team.myidentifier:
                name = self.team.users[self.team.myidentifier].name
                name_plain = self.team.users[self.team.myidentifier].name
            elif self.message_json['user'] in self.team.users:
                u = self.team.users[self.message_json['user']]
                if u.is_bot:
                    name = "{} :]".format(u.formatted_name())
                else:
                    name = "{}".format(u.formatted_name())
                name_plain = "{}".format(u.formatted_name(enable_color=False))
        elif 'username' in self.message_json:
            name = "-{}-".format(self.message_json["username"])
            name_plain = "{}".format(self.message_json["username"])
        elif 'service_name' in self.message_json:
            name = "-{}-".format(self.message_json["service_name"])
            name_plain = "{}".format(self.message_json["service_name"])
        else:
            name = ""
            name_plain = ""
        return (name, name_plain)

    def add_reaction(self, reaction, user):
        m = self.message_json.get('reactions', None)
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
        m = self.message_json.get('reactions', None)
        if m:
            for r in m:
                if r["name"] == reaction and user in r["users"]:
                    r["users"].remove(user)
        else:
            pass


class SlackThreadMessage(SlackMessage):

    def __init__(self, parent_id, *args):
        super(SlackThreadMessage, self).__init__(*args)
        self.parent_id = parent_id


class WeeSlackMetadata(object):
    """
    A simple container that we pickle/unpickle to hold data.
    """

    def __init__(self, meta):
        self.meta = meta

    def jsonify(self):
        return self.meta


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
        else:
            s = self.__str__()
            if s < other:
                return -1
            elif s > other:
                return 1
            elif s == other:
                return 0

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


def handle_rtmstart(login_data, eventrouter):
    """
    This handles the main entry call to slack, rtm.start
    """
    if login_data["ok"]:

        metadata = pickle.loads(login_data["wee_slack_request_metadata"])

        # Let's reuse a team if we have it already.
        th = SlackTeam.generate_team_hash(login_data['self']['name'], login_data['team']['domain'])
        if not eventrouter.teams.get(th):

            users = {}
            for item in login_data["users"]:
                users[item["id"]] = SlackUser(**item)
                # users.append(SlackUser(**item))

            bots = {}
            for item in login_data["bots"]:
                bots[item["id"]] = SlackBot(**item)

            channels = {}
            for item in login_data["channels"]:
                channels[item["id"]] = SlackChannel(eventrouter, **item)

            for item in login_data["ims"]:
                channels[item["id"]] = SlackDMChannel(eventrouter, users, **item)

            for item in login_data["groups"]:
                if item["name"].startswith('mpdm-'):
                    channels[item["id"]] = SlackMPDMChannel(eventrouter, **item)
                else:
                    channels[item["id"]] = SlackGroupChannel(eventrouter, **item)

            t = SlackTeam(
                eventrouter,
                metadata.token,
                login_data['url'],
                login_data["team"]["domain"],
                login_data["self"]["name"],
                login_data["self"]["id"],
                users,
                bots,
                channels,
                muted_channels=login_data["self"]["prefs"]["muted_channels"],
                highlight_words=login_data["self"]["prefs"]["highlight_words"],
            )
            eventrouter.register_team(t)

        else:
            t = eventrouter.teams.get(th)
            t.set_reconnect_url(login_data['url'])
            t.connect()

        # web_socket_url = login_data['url']
        # try:
        #    ws = create_connection(web_socket_url, sslopt=sslopt_ca_certs)
        #    w.hook_fd(ws.sock._sock.fileno(), 1, 0, 0, "receive_ws_callback", t.get_team_hash())
        #    #ws_hook = w.hook_fd(ws.sock._sock.fileno(), 1, 0, 0, "receive_ws_callback", pickle.dumps(t))
        #    ws.sock.setblocking(0)
        #    t.attach_websocket(ws)
        #    t.set_connected()
        # except Exception as e:
        #    dbg("websocket connection error: {}".format(e))
        #    return False

        t.buffer_prnt('Connected to Slack')
        t.buffer_prnt('{:<20} {}'.format("Websocket URL", login_data["url"]))
        t.buffer_prnt('{:<20} {}'.format("User name", login_data["self"]["name"]))
        t.buffer_prnt('{:<20} {}'.format("User ID", login_data["self"]["id"]))
        t.buffer_prnt('{:<20} {}'.format("Team name", login_data["team"]["name"]))
        t.buffer_prnt('{:<20} {}'.format("Team domain", login_data["team"]["domain"]))
        t.buffer_prnt('{:<20} {}'.format("Team id", login_data["team"]["id"]))

        dbg("connected to {}".format(t.domain))

    # self.identifier = self.domain


def handle_groupshistory(message_json, eventrouter, **kwargs):
    handle_history(message_json, eventrouter, **kwargs)


def handle_channelshistory(message_json, eventrouter, **kwargs):
    handle_history(message_json, eventrouter, **kwargs)


def handle_imhistory(message_json, eventrouter, **kwargs):
    handle_history(message_json, eventrouter, **kwargs)


def handle_history(message_json, eventrouter, **kwargs):
    request_metadata = pickle.loads(message_json["wee_slack_request_metadata"])
    kwargs['team'] = eventrouter.teams[request_metadata.team_hash]
    kwargs['channel'] = kwargs['team'].channels[request_metadata.channel_identifier]
    try:
        clear = request_metadata.clear
    except:
        clear = False
    dbg(clear)
    kwargs['output_type'] = "backlog"
    if clear:
        w.buffer_clear(kwargs['channel'].channel_buffer)
    for message in reversed(message_json["messages"]):
        process_message(message, eventrouter, **kwargs)

###### New/converted process_ and subprocess_ methods


def process_reconnect_url(message_json, eventrouter, **kwargs):
    kwargs['team'].set_reconnect_url(message_json['url'])


def process_manual_presence_change(message_json, eventrouter, **kwargs):
    process_presence_change(message_json, eventrouter, **kwargs)


def process_presence_change(message_json, eventrouter, **kwargs):
    kwargs["user"].presence = message_json["presence"]


def process_pref_change(message_json, eventrouter, **kwargs):
    team = kwargs["team"]
    if message_json['name'] == 'muted_channels':
        team.set_muted_channels(message_json['value'])
    elif message_json['name'] == 'highlight_words':
        team.set_highlight_words(message_json['value'])
    else:
        dbg("Preference change not implemented: {}\n".format(message_json['name']))


def process_user_typing(message_json, eventrouter, **kwargs):
    channel = kwargs["channel"]
    team = kwargs["team"]
    if channel:
        channel.set_typing(team.users.get(message_json["user"]).name)
        w.bar_item_update("slack_typing_notice")


def process_team_join(message_json, eventrouter, **kwargs):
    user = message_json['user']
    team = kwargs["team"]
    team.users[user["id"]] = SlackUser(**user)


def process_pong(message_json, eventrouter, **kwargs):
    pass


def process_message(message_json, eventrouter, store=True, **kwargs):
    channel = kwargs["channel"]
    team = kwargs["team"]
    # try:
    #  send these subtype messages elsewhere
    known_subtypes = [
        'thread_message',
        'message_replied',
        'message_changed',
        'message_deleted',
        'channel_join',
        'channel_leave',
        'channel_topic',
        # 'group_join',
        # 'group_leave',
    ]
    if "thread_ts" in message_json and "reply_count" not in message_json:
        message_json["subtype"] = "thread_message"

    subtype = message_json.get("subtype", None)
    if subtype and subtype in known_subtypes:
        f = eval('subprocess_' + subtype)
        f(message_json, eventrouter, channel, team)

    else:
        message = SlackMessage(message_json, team, channel)
        text = message.render()
        dbg("Rendered message: %s" % text)
        dbg("Sender: %s (%s)" % (message.sender, message.sender_plain))

        # Handle actions (/me).
        # We don't use `subtype` here because creating the SlackMessage may
        # have changed the subtype based on the detected message contents.
        if message.message_json.get('subtype') == 'me_message':
            try:
                channel.unread_count_display += 1
            except:
                channel.unread_count_display = 1
            channel.buffer_prnt(w.prefix("action").rstrip(), text, message.ts, tag_nick=message.sender_plain, **kwargs)

        else:
            suffix = ''
            if 'edited' in message_json:
                suffix = ' (edited)'
            try:
                channel.unread_count_display += 1
            except:
                channel.unread_count_display = 1
            channel.buffer_prnt(message.sender, text + suffix, message.ts, tag_nick=message.sender_plain, **kwargs)

        if store:
            channel.store_message(message, team)
        dbg("NORMAL REPLY {}".format(message_json))
    # except:
    #    channel.buffer_prnt("WEE-SLACK-ERROR", json.dumps(message_json), message_json["ts"], **kwargs)
    #    traceback.print_exc()


def subprocess_thread_message(message_json, eventrouter, channel, team):
    # print ("THREADED: " + str(message_json))
    parent_ts = message_json.get('thread_ts', None)
    if parent_ts:
        parent_message = channel.messages.get(SlackTS(parent_ts), None)
        if parent_message:
            message = SlackThreadMessage(parent_ts, message_json, team, channel)
            parent_message.submessages.append(message)
            channel.hash_message(parent_ts)
            channel.store_message(message, team)
            channel.change_message(parent_ts)

            text = message.render()
            # channel.buffer_prnt(message.sender, text, message.ts, **kwargs)
            if parent_message.thread_channel:
                parent_message.thread_channel.buffer_prnt(message.sender, text, message.ts)

#    channel = channels.find(message_json["channel"])
#    server = channel.server
#    #threadinfo = channel.get_message(message_json["thread_ts"])
#    message = Message(message_json, server=server, channel=channel)
#    dbg(message, main_buffer=True)
#
#    orig = channel.get_message(message_json['thread_ts'])
#    if orig[0]:
#        channel.get_message(message_json['thread_ts'])[2].add_thread_message(message)
#    else:
#        dbg("COULDN'T find orig message {}".format(message_json['thread_ts']), main_buffer=True)

    # if threadinfo[0]:
    #    channel.messages[threadinfo[1]].become_thread()
    #    message_json["item"]["ts"], message_json)
    # channel.change_message(message_json["thread_ts"], None, message_json["text"])
    # channel.become_thread(message_json["item"]["ts"], message_json)


def subprocess_channel_join(message_json, eventrouter, channel, team):
    joinprefix = w.prefix("join")
    message = SlackMessage(message_json, team, channel, override_sender=joinprefix)
    channel.buffer_prnt(joinprefix, message.render(), message_json["ts"], tagset='joinleave')
    channel.user_joined(message_json['user'])


def subprocess_channel_leave(message_json, eventrouter, channel, team):
    leaveprefix = w.prefix("quit")
    message = SlackMessage(message_json, team, channel, override_sender=leaveprefix)
    channel.buffer_prnt(leaveprefix, message.render(), message_json["ts"], tagset='joinleave')
    channel.user_left(message_json['user'])
    # channel.update_nicklist(message_json['user'])
    # channel.update_nicklist()


def subprocess_message_replied(message_json, eventrouter, channel, team):
    pass


def subprocess_message_changed(message_json, eventrouter, channel, team):
    m = message_json.get("message", None)
    if m:
        new_message = m
        # message = SlackMessage(new_message, team, channel)
        if "attachments" in m:
            message_json["attachments"] = m["attachments"]
        if "text" in m:
            if "text" in message_json:
                message_json["text"] += m["text"]
                dbg("added text!")
            else:
                message_json["text"] = m["text"]
        if "fallback" in m:
            if "fallback" in message_json:
                message_json["fallback"] += m["fallback"]
            else:
                message_json["fallback"] = m["fallback"]

    text_before = (len(new_message['text']) > 0)
    new_message["text"] += unwrap_attachments(message_json, text_before)
    if "edited" in new_message:
        channel.change_message(new_message["ts"], new_message["text"], ' (edited)')
    else:
        channel.change_message(new_message["ts"], new_message["text"])


def subprocess_message_deleted(message_json, eventrouter, channel, team):
    channel.change_message(message_json["deleted_ts"], "(deleted)", '')


def subprocess_channel_topic(message_json, eventrouter, channel, team):
    text = unfurl_refs(message_json["text"], ignore_alt_text=False)
    channel.buffer_prnt(w.prefix("network").rstrip(), text, message_json["ts"], tagset="muted")
    channel.render_topic(message_json["topic"])


def process_reply(message_json, eventrouter, **kwargs):
    dbg('processing reply')
    team = kwargs["team"]
    identifier = message_json["reply_to"]
    try:
        original_message_json = team.ws_replies[identifier]
        del team.ws_replies[identifier]
        if "ts" in message_json:
            original_message_json["ts"] = message_json["ts"]
        else:
            dbg("no reply ts {}".format(message_json))

        c = original_message_json.get('channel', None)
        channel = team.channels[c]
        m = SlackMessage(original_message_json, team, channel)

        # if "type" in message_json:
        #    if message_json["type"] == "message" and "channel" in message_json.keys():
        #        message_json["ts"] = message_json["ts"]
        #        channels.find(message_json["channel"]).store_message(m, from_me=True)

        #        channels.find(message_json["channel"]).buffer_prnt(server.nick, m.render(), m.ts)

        process_message(m.message_json, eventrouter, channel=channel, team=team)
        channel.mark_read(update_remote=True, force=True)
        dbg("REPLY {}".format(message_json))
    except KeyError:
        dbg("Unexpected reply {}".format(message_json))


def process_channel_marked(message_json, eventrouter, **kwargs):
    """
    complete
    """
    channel = kwargs["channel"]
    ts = message_json.get("ts", None)
    if ts:
        channel.mark_read(ts=ts, force=True, update_remote=False)
    else:
        dbg("tried to mark something weird {}".format(message_json))


def process_group_marked(message_json, eventrouter, **kwargs):
    process_channel_marked(message_json, eventrouter, **kwargs)


def process_im_marked(message_json, eventrouter, **kwargs):
    process_channel_marked(message_json, eventrouter, **kwargs)


def process_mpim_marked(message_json, eventrouter, **kwargs):
    process_channel_marked(message_json, eventrouter, **kwargs)


def process_channel_joined(message_json, eventrouter, **kwargs):
    item = message_json["channel"]
    kwargs['team'].channels[item["id"]].update_from_message_json(item)
    kwargs['team'].channels[item["id"]].open()


def process_channel_created(message_json, eventrouter, **kwargs):
    item = message_json["channel"]
    c = SlackChannel(eventrouter, team=kwargs["team"], **item)
    kwargs['team'].channels[item["id"]] = c
    kwargs['team'].buffer_prnt('Channel created: {}'.format(c.slack_name))


def process_channel_rename(message_json, eventrouter, **kwargs):
    item = message_json["channel"]
    channel = kwargs['team'].channels[item["id"]]
    channel.slack_name = message_json['channel']['name']


def process_im_created(message_json, eventrouter, **kwargs):
    team = kwargs['team']
    item = message_json["channel"]
    c = SlackDMChannel(eventrouter, team=team, users=team.users, **item)
    team.channels[item["id"]] = c
    kwargs['team'].buffer_prnt('IM channel created: {}'.format(c.name))


def process_im_open(message_json, eventrouter, **kwargs):
    channel = kwargs['channel']
    item = message_json
    kwargs['team'].channels[item["channel"]].check_should_open(True)
    w.buffer_set(channel.channel_buffer, "hotlist", "2")


def process_im_close(message_json, eventrouter, **kwargs):
    item = message_json
    cbuf = kwargs['team'].channels[item["channel"]].channel_buffer
    eventrouter.weechat_controller.unregister_buffer(cbuf, False, True)


def process_group_joined(message_json, eventrouter, **kwargs):
    item = message_json["channel"]
    if item["name"].startswith("mpdm-"):
        c = SlackMPDMChannel(eventrouter, team=kwargs["team"], **item)
    else:
        c = SlackGroupChannel(eventrouter, team=kwargs["team"], **item)
    kwargs['team'].channels[item["id"]] = c
    kwargs['team'].channels[item["id"]].open()


def process_reaction_added(message_json, eventrouter, **kwargs):
    channel = kwargs['team'].channels[message_json["item"]["channel"]]
    if message_json["item"].get("type") == "message":
        ts = SlackTS(message_json['item']["ts"])

        message = channel.messages.get(ts, None)
        if message:
            message.add_reaction(message_json["reaction"], message_json["user"])
            channel.change_message(ts)
    else:
        dbg("reaction to item type not supported: " + str(message_json))


def process_reaction_removed(message_json, eventrouter, **kwargs):
    channel = kwargs['team'].channels[message_json["item"]["channel"]]
    if message_json["item"].get("type") == "message":
        ts = SlackTS(message_json['item']["ts"])

        message = channel.messages.get(ts, None)
        if message:
            message.remove_reaction(message_json["reaction"], message_json["user"])
            channel.change_message(ts)
    else:
        dbg("Reaction to item type not supported: " + str(message_json))

###### New module/global methods


def render(message_json, team, channel, force=False):
    # If we already have a rendered version in the object, just return that.
    if not force and message_json.get("_rendered_text", ""):
        return message_json["_rendered_text"]
    else:
        # server = servers.find(message_json["_server"])

        if "fallback" in message_json:
            text = message_json["fallback"]
        elif "text" in message_json:
            if message_json['text'] is not None:
                text = message_json["text"]
            else:
                text = ""
        else:
            text = ""

        text = unfurl_refs(text, ignore_alt_text=config.unfurl_ignore_alt_text)

        text_before = (len(text) > 0)
        text += unfurl_refs(unwrap_attachments(message_json, text_before), ignore_alt_text=config.unfurl_ignore_alt_text)

        text = text.lstrip()
        text = text.replace("\t", "    ")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&amp;", "&")
        text = re.sub(r'(^| )\*([^*]+)\*([^a-zA-Z0-9_]|$)',
                      r'\1{}\2{}\3'.format(w.color('bold'), w.color('-bold')), text)
        text = re.sub(r'(^| )_([^_]+)_([^a-zA-Z0-9_]|$)',
                      r'\1{}\2{}\3'.format(w.color('underline'), w.color('-underline')), text)

#        if self.threads:
#            text += " [Replies: {} Thread ID: {} ] ".format(len(self.threads), self.thread_id)
#            #for thread in self.threads:

        text += create_reaction_string(message_json.get("reactions", ""))
        message_json["_rendered_text"] = text
        return text


def linkify_text(message, team, channel):
    # The get_username_map function is a bit heavy, but this whole
    # function is only called on message send..
    usernames = team.get_username_map()
    channels = team.get_channel_map()
    message = message.replace('\x02', '*').replace('\x1F', '_').split(' ')
    for item in enumerate(message):
        targets = re.match('^\s*([@#])([\w.-]+[\w. -])(\W*)', item[1])
        if targets and targets.groups()[0] == '@':
            named = targets.groups()
            if named[1] in ["group", "channel", "here"]:
                message[item[0]] = "<!{}>".format(named[1])
            else:
                try:
                    if usernames[named[1]]:
                        message[item[0]] = "<@{}>{}".format(usernames[named[1]], named[2])
                except:
                    message[item[0]] = "@{}{}".format(named[1], named[2])
        if targets and targets.groups()[0] == '#':
            named = targets.groups()
            try:
                if channels[named[1]]:
                    message[item[0]] = "<#{}|{}>{}".format(channels[named[1]], named[1], named[2])
            except:
                message[item[0]] = "#{}{}".format(named[1], named[2])

    # dbg(message)
    return " ".join(message)


def unfurl_refs(text, ignore_alt_text=False):
    """
    input : <@U096Q7CQM|someuser> has joined the channel
    ouput : someuser has joined the channel
    """
    # Find all strings enclosed by <>
    #  - <https://example.com|example with spaces>
    #  - <#C2147483705|#otherchannel>
    #  - <@U2147483697|@othernick>
    # Test patterns lives in ./_pytest/test_unfurl.py
    matches = re.findall(r"(<[@#]?(?:[^<]*)>)", text)
    for m in matches:
        # Replace them with human readable strings
        text = text.replace(m, unfurl_ref(m[1:-1], ignore_alt_text))
    return text


def unfurl_ref(ref, ignore_alt_text=False):
    id = ref.split('|')[0]
    display_text = ref
    if ref.find('|') > -1:
        if ignore_alt_text:
            display_text = resolve_ref(id)
        else:
            if id.startswith("#C"):
                display_text = "#{}".format(ref.split('|')[1])
            elif id.startswith("@U"):
                display_text = ref.split('|')[1]
            else:
                url, desc = ref.split('|', 1)
                display_text = "{} ({})".format(url, desc)
    else:
        display_text = resolve_ref(ref)
    return display_text


def unwrap_attachments(message_json, text_before):
    attachment_text = ''
    a = message_json.get("attachments", None)
    if a:
        if text_before:
            attachment_text = '\n'
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
            title = attachment.get('title', None)
            title_link = attachment.get('title_link', None)
            if title and title_link:
                t.append('%s%s (%s)' % (prepend_title_text, title, title_link,))
                prepend_title_text = ''
            elif title and not title_link:
                t.append(prepend_title_text + title)
                prepend_title_text = ''
            t.append(attachment.get("from_url", ""))

            atext = attachment.get("text", None)
            if atext:
                tx = re.sub(r' *\n[\n ]+', '\n', atext)
                t.append(prepend_title_text + tx)
                prepend_title_text = ''
            fields = attachment.get("fields", None)
            if fields:
                for f in fields:
                    if f['title'] != '':
                        t.append('%s %s' % (f['title'], f['value'],))
                    else:
                        t.append(f['value'])
            fallback = attachment.get("fallback", None)
            if t == [] and fallback:
                t.append(fallback)
            attachment_text += "\n".join([x.strip() for x in t if x])
    return attachment_text


def resolve_ref(ref):
    # TODO: This hack to use eventrouter needs to go
    # this resolver should probably move to the slackteam or eventrouter itself
    # global EVENTROUTER
    if 'EVENTROUTER' in globals():
        e = EVENTROUTER
        if ref.startswith('@U') or ref.startswith('@W'):
            for t in e.teams.keys():
                if ref[1:] in e.teams[t].users:
                    # try:
                    return "@{}".format(e.teams[t].users[ref[1:]].name)
                    # except:
                    #    dbg("NAME: {}".format(ref))
        elif ref.startswith('#C'):
            for t in e.teams.keys():
                if ref[1:] in e.teams[t].channels:
                    # try:
                    return "{}".format(e.teams[t].channels[ref[1:]].name)
                    # except:
                    #    dbg("CHANNEL: {}".format(ref))

        # Something else, just return as-is
    return ref


def create_reaction_string(reactions):
    count = 0
    if not isinstance(reactions, list):
        reaction_string = " [{}]".format(reactions)
    else:
        reaction_string = ' ['
        for r in reactions:
            if len(r["users"]) > 0:
                count += 1
                if config.show_reaction_nicks:
                    nicks = [resolve_ref("@{}".format(user)) for user in r["users"]]
                    users = "({})".format(",".join(nicks))
                else:
                    users = len(r["users"])
                reaction_string += ":{}:{} ".format(r["name"], users)
        reaction_string = reaction_string[:-1] + ']'
    if count == 0:
        reaction_string = ''
    return reaction_string


def modify_buffer_line(buffer, new_line, timestamp, time_id):
    # get a pointer to this buffer's lines
    own_lines = w.hdata_pointer(w.hdata_get('buffer'), buffer, 'own_lines')
    if own_lines:
        # get a pointer to the last line
        line_pointer = w.hdata_pointer(w.hdata_get('lines'), own_lines, 'last_line')
        # hold the structure of a line and of line data
        struct_hdata_line = w.hdata_get('line')
        struct_hdata_line_data = w.hdata_get('line_data')

        while line_pointer:
            # get a pointer to the data in line_pointer via layout of struct_hdata_line
            data = w.hdata_pointer(struct_hdata_line, line_pointer, 'data')
            if data:
                line_timestamp = w.hdata_time(struct_hdata_line_data, data, 'date')
                line_time_id = w.hdata_integer(struct_hdata_line_data, data, 'date_printed')
                # prefix = w.hdata_string(struct_hdata_line_data, data, 'prefix')

                if timestamp == int(line_timestamp) and int(time_id) == line_time_id:
                    # w.prnt("", "found matching time date is {}, time is {} ".format(timestamp, line_timestamp))
                    w.hdata_update(struct_hdata_line_data, data, {"message": new_line})
                    break
                else:
                    pass
            # move backwards one line and try again - exit the while if you hit the end
            line_pointer = w.hdata_move(struct_hdata_line, line_pointer, -1)
    return w.WEECHAT_RC_OK


def modify_print_time(buffer, new_id, time):
    """
    This overloads the time printed field to let us store the slack
    per message unique id that comes after the "." in a slack ts
    """

    # get a pointer to this buffer's lines
    own_lines = w.hdata_pointer(w.hdata_get('buffer'), buffer, 'own_lines')
    if own_lines:
        # get a pointer to the last line
        line_pointer = w.hdata_pointer(w.hdata_get('lines'), own_lines, 'last_line')
        # hold the structure of a line and of line data
        struct_hdata_line = w.hdata_get('line')
        struct_hdata_line_data = w.hdata_get('line_data')

        # get a pointer to the data in line_pointer via layout of struct_hdata_line
        data = w.hdata_pointer(struct_hdata_line, line_pointer, 'data')
        if data:
            w.hdata_update(struct_hdata_line_data, data, {"date_printed": new_id})

    return w.WEECHAT_RC_OK


def tag(tagset, user=None):
    if user:
        user.replace(" ", "_")
        default_tag = "nick_" + user
    else:
        default_tag = 'nick_unknown'
    tagsets = {
        # when replaying something old
        "backlog": "no_highlight,notify_none,logger_backlog_end",
        # when posting messages to a muted channel
        "muted": "no_highlight,notify_none,logger_backlog_end",
        # when my nick is in the message
        "highlightme": "notify_highlight,log1",
        # when receiving a direct message
        "dm": "notify_private,notify_message,log1,irc_privmsg",
        "dmfromme": "notify_none,log1,irc_privmsg",
        # when this is a join/leave, attach for smart filter ala:
        # if user in [x.strip() for x in w.prefix("join"), w.prefix("quit")]
        "joinleave": "irc_smart_filter,no_highlight",
        # catchall ?
        "default": "notify_message,log1",
    }
    return default_tag + "," + tagsets[tagset]

###### New/converted command_ commands


@slack_buffer_or_ignore
def part_command_cb(data, current_buffer, args):
    data = decode_from_utf8(data)
    args = decode_from_utf8(args)
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
        e.weechat_controller.unregister_buffer(current_buffer, update_remote=True, close_buffer=True)
    return w.WEECHAT_RC_OK_EAT


@slack_buffer_or_ignore
def topic_command_cb(data, current_buffer, args):
    n = len(args.split())
    if n < 2:
        channel = channels.find(current_buffer)
        if channel:
            w.prnt(current_buffer, 'Topic for {} is "{}"'.format(channel.name, channel.topic))
        return w.WEECHAT_RC_OK_EAT
    elif command_topic(data, current_buffer, args.split(None, 1)[1]):
        return w.WEECHAT_RC_OK_EAT
    else:
        return w.WEECHAT_RC_ERROR


@slack_buffer_required
def command_topic(data, current_buffer, args):
    """
    Change the topic of a channel
    /slack topic [<channel>] [<topic>|-delete]
    """
    data = decode_from_utf8(data)
    args = decode_from_utf8(args)
    e = EVENTROUTER
    team = e.weechat_controller.buffers[current_buffer].team
    # server = servers.find(current_domain_name())
    args = args.split(' ')
    if len(args) > 2 and args[1].startswith('#'):
        cmap = team.get_channel_map()
        channel_name = args[1][1:]
        channel = team.channels[cmap[channel_name]]
        topic = " ".join(args[2:])
    else:
        channel = e.weechat_controller.buffers[current_buffer]
        topic = " ".join(args[1:])

    if channel:
        if topic == "-delete":
            topic = ''
        s = SlackRequest(team.token, "channels.setTopic", {"channel": channel.identifier, "topic": topic}, team_hash=team.team_hash)
        EVENTROUTER.receive(s)
        return w.WEECHAT_RC_OK_EAT
    else:
        return w.WEECHAT_RC_ERROR_EAT


@slack_buffer_or_ignore
def me_command_cb(data, current_buffer, args):
    data = decode_from_utf8(data)
    args = decode_from_utf8(args)
    message = "_{}_".format(args.split(' ', 1)[1])
    buffer_input_callback("EVENTROUTER", current_buffer, message)
    return w.WEECHAT_RC_OK_EAT


@slack_buffer_or_ignore
def msg_command_cb(data, current_buffer, args):
    data = decode_from_utf8(data)
    args = decode_from_utf8(args)
    dbg("msg_command_cb")
    aargs = args.split(None, 2)
    who = aargs[1]
    command_talk(data, current_buffer, who)

    if len(aargs) > 2:
        message = aargs[2]
        team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
        cmap = team.get_channel_map()
        if who in cmap:
            channel = team.channels[cmap[channel]]
            channel.send_message(message)
    return w.WEECHAT_RC_OK_EAT


@slack_buffer_or_ignore
def command_talk(data, current_buffer, args):
    """
    Open a chat with the specified user
    /slack talk [user]
    """

    data = decode_from_utf8(data)
    args = decode_from_utf8(args)
    e = EVENTROUTER
    team = e.weechat_controller.buffers[current_buffer].team
    channel_name = args.split(' ')[1]
    c = team.get_channel_map()
    if channel_name not in c:
        u = team.get_username_map()
        if channel_name in u:
            s = SlackRequest(team.token, "im.open", {"user": u[channel_name]}, team_hash=team.team_hash)
            EVENTROUTER.receive(s)
            dbg("found user")
            # refresh channel map here
            c = team.get_channel_map()

    if channel_name.startswith('#'):
        channel_name = channel_name[1:]
    if channel_name in c:
        chan = team.channels[c[channel_name]]
        chan.open()
        if config.switch_buffer_on_join:
            w.buffer_set(chan.channel_buffer, "display", "1")
        return w.WEECHAT_RC_OK_EAT
    return w.WEECHAT_RC_OK_EAT


def command_showmuted(data, current_buffer, args):
    current = w.current_buffer()
    w.prnt(EVENTROUTER.weechat_controller.buffers[current].team.channel_buffer, str(EVENTROUTER.weechat_controller.buffers[current].team.muted_channels))


def thread_command_callback(data, current_buffer, args):
    data = decode_from_utf8(data)
    args = decode_from_utf8(args)
    current = w.current_buffer()
    channel = EVENTROUTER.weechat_controller.buffers.get(current)
    if channel:
        args = args.split()
        if args[0] == '/thread':
            if len(args) == 2:
                try:
                    pm = channel.messages[SlackTS(args[1])]
                except:
                    pm = channel.hashed_messages[args[1]]
                tc = SlackThreadChannel(EVENTROUTER, pm)
                pm.thread_channel = tc
                tc.open()
                # tc.create_buffer()
                return w.WEECHAT_RC_OK_EAT
        elif args[0] == '/reply':
            count = int(args[1])
            msg = " ".join(args[2:])
            mkeys = channel.sorted_message_keys()
            mkeys.reverse()
            parent_id = str(mkeys[count - 1])
            channel.send_message(msg, request_dict_ext={"thread_ts": parent_id})
            return w.WEECHAT_RC_OK_EAT
        w.prnt(current, "Invalid thread command.")
        return w.WEECHAT_RC_OK_EAT


def rehistory_command_callback(data, current_buffer, args):
    data = decode_from_utf8(data)
    args = decode_from_utf8(args)
    current = w.current_buffer()
    channel = EVENTROUTER.weechat_controller.buffers.get(current)
    channel.got_history = False
    w.buffer_clear(channel.channel_buffer)
    channel.get_history()
    return w.WEECHAT_RC_OK_EAT


@slack_buffer_required
def hide_command_callback(data, current_buffer, args):
    data = decode_from_utf8(data)
    args = decode_from_utf8(args)
    c = EVENTROUTER.weechat_controller.buffers.get(current_buffer, None)
    if c:
        name = c.formatted_name(style='long_default')
        if name in config.distracting_channels:
            w.buffer_set(c.channel_buffer, "hidden", "1")
    return w.WEECHAT_RC_OK_EAT


def slack_command_cb(data, current_buffer, args):
    data = decode_from_utf8(data)
    args = decode_from_utf8(args)
    a = args.split(' ', 1)
    if len(a) > 1:
        function_name, args = a[0], args
    else:
        function_name, args = a[0], args

    try:
        EVENTROUTER.cmds[function_name]("", current_buffer, args)
    except KeyError:
        w.prnt("", "Command not found: " + function_name)
    return w.WEECHAT_RC_OK


@slack_buffer_required
def command_distracting(data, current_buffer, args):
    channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer, None)
    if channel:
        fullname = channel.formatted_name(style="long_default")
    if config.distracting_channels.count(fullname) == 0:
        config.distracting_channels.append(fullname)
    else:
        config.distracting_channels.pop(config.distracting_channels.index(fullname))
    save_distracting_channels()


def save_distracting_channels():
    w.config_set_plugin('distracting_channels', ','.join(config.distracting_channels))


@slack_buffer_required
def command_slash(data, current_buffer, args):
    """
    Support for custom slack commands
    /slack slash /customcommand arg1 arg2 arg3
    """
    e = EVENTROUTER
    channel = e.weechat_controller.buffers.get(current_buffer, None)
    if channel:
        team = channel.team

        if args is None:
            server.buffer_prnt("Usage: /slack slash /someslashcommand [arguments...].")
            return

        split_args = args.split(None, 2)
        command = split_args[1]
        text = split_args[2] if len(split_args) > 2 else ""

        s = SlackRequest(team.token, "chat.command", {"command": command, "text": text, 'channel': channel.identifier}, team_hash=team.team_hash, channel_identifier=channel.identifier)
        EVENTROUTER.receive(s)


@slack_buffer_required
def command_mute(data, current_buffer, args):
    current = w.current_buffer()
    channel_id = EVENTROUTER.weechat_controller.buffers[current].identifier
    team = EVENTROUTER.weechat_controller.buffers[current].team
    if channel_id not in team.muted_channels:
        team.muted_channels.add(channel_id)
    else:
        team.muted_channels.discard(channel_id)
    s = SlackRequest(team.token, "users.prefs.set", {"name": "muted_channels", "value": ",".join(team.muted_channels)}, team_hash=team.team_hash, channel_identifier=channel_id)
    EVENTROUTER.receive(s)


@slack_buffer_required
def command_openweb(data, current_buffer, args):
    # if done from server buffer, open slack for reals
    channel = EVENTROUTER.weechat_controller.buffers[current_buffer]
    if isinstance(channel, SlackTeam):
        url = "https://{}".format(channel.team.domain)
    else:
        now = SlackTS()
        url = "https://{}/archives/{}/p{}000000".format(channel.team.domain, channel.slack_name, now.majorstr())
    w.prnt_date_tags(channel.team.channel_buffer, SlackTS().major, "openweb,logger_backlog_end,notify_none", url)


def command_nodistractions(data, current_buffer, args):
    global hide_distractions
    hide_distractions = not hide_distractions
    if config.distracting_channels != ['']:
        for channel in config.distracting_channels:
            dbg('hiding channel {}'.format(channel))
            # try:
            for c in EVENTROUTER.weechat_controller.buffers.itervalues():
                if c == channel:
                    dbg('found channel {} to hide'.format(channel))
                    w.buffer_set(c.channel_buffer, "hidden", str(int(hide_distractions)))
            # except:
            #    dbg("Can't hide channel {} .. removing..".format(channel), main_buffer=True)
#                config.distracting_channels.pop(config.distracting_channels.index(channel))
#                save_distracting_channels()


@slack_buffer_required
def command_upload(data, current_buffer, args):
    channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer)
    url = 'https://slack.com/api/files.upload'
    fname = args.split(' ', 1)
    file_path = os.path.expanduser(fname[1])
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
    if ' ' in file_path:
        file_path = file_path.replace(' ', '\ ')

    command = 'curl -F file=@{} -F channels={} -F token={} {}'.format(file_path, channel.identifier, team.token, url)
    w.hook_process(command, config.slack_timeout, '', '')


def away_command_cb(data, current_buffer, args):
    data = decode_from_utf8(data)
    args = decode_from_utf8(args)
    # TODO: reimplement all.. maybe
    (all, message) = re.match("^/away(?:\s+(-all))?(?:\s+(.+))?", args).groups()
    if message is None:
        command_back(data, current_buffer, args)
    else:
        command_away(data, current_buffer, args)
    return w.WEECHAT_RC_OK


@slack_buffer_required
def command_away(data, current_buffer, args):
    """
    Sets your status as 'away'
    /slack away
    """
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
    s = SlackRequest(team.token, "presence.set", {"presence": "away"}, team_hash=team.team_hash)
    EVENTROUTER.receive(s)


@slack_buffer_required
def command_status(data, current_buffer, args):
    """
    Lets you set your Slack Status (not to be confused with away/here)
    /slack status [emoji] [status_message]
    """
    e = EVENTROUTER
    channel = e.weechat_controller.buffers.get(current_buffer, None)
    if channel:
        team = channel.team

        if args is None:
            server.buffer_prnt("Usage: /slack status [status emoji] [status text].")
            return

        split_args = args.split(None, 2)
        emoji = split_args[1] if len(split_args) > 1 else ""
        text = split_args[2] if len(split_args) > 2 else ""

        profile = {"status_text":text,"status_emoji":emoji}

        s = SlackRequest(team.token, "users.profile.set", {"profile": profile}, team_hash=team.team_hash, channel_identifier=channel.identifier)
        EVENTROUTER.receive(s)


@slack_buffer_required
def command_back(data, current_buffer, args):
    """
    Sets your status as 'back'
    /slack back
    """
    team = EVENTROUTER.weechat_controller.buffers[current_buffer].team
    s = SlackRequest(team.token, "presence.set", {"presence": "active"}, team_hash=team.team_hash)
    EVENTROUTER.receive(s)


@slack_buffer_required
def label_command_cb(data, current_buffer, args):
    data = decode_from_utf8(data)
    args = decode_from_utf8(args)
    channel = EVENTROUTER.weechat_controller.buffers.get(current_buffer)
    if channel and channel.type == 'thread':
        aargs = args.split(None, 2)
        new_name = " +" + aargs[1]
        channel.label = new_name
        w.buffer_set(channel.channel_buffer, "short_name", new_name)


def command_p(data, current_buffer, args):
    args = args.split(' ', 1)[1]
    w.prnt("", "{}".format(eval(args)))

###### NEW EXCEPTIONS


class ProcessNotImplemented(Exception):
    """
    Raised when we try to call process_(something), but
    (something) has not been defined as a function.
    """
    def __init__(self, function_name):
        super(ProcessNotImplemented, self).__init__(function_name)


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
    if slack_debug is not None:
        w.buffer_set(slack_debug, "display", "1")
    else:
        debug_string = None
        slack_debug = w.buffer_new("slack-debug", "", "", "closed_slack_debug_buffer_cb", "")
        w.buffer_set(slack_debug, "notify", "0")


def load_emoji():
    try:
        global EMOJI
        DIR = w.info_get("weechat_dir", "")
        # no idea why this does't work w/o checking the type?!
        dbg(type(DIR), 0)
        ef = open('{}/weemoji.json'.format(DIR), 'r')
        EMOJI = json.loads(ef.read())
        ef.close()
    except:
        dbg("Unexpected error: {}".format(sys.exc_info()), 5)
    return w.WEECHAT_RC_OK


def setup_hooks():
    cmds = {k[8:]: v for k, v in globals().items() if k.startswith("command_")}

    w.bar_item_new('slack_typing_notice', 'typing_bar_item_cb', '')

    w.hook_timer(1000, 0, 0, "typing_update_cb", "")
    w.hook_timer(1000, 0, 0, "buffer_list_update_callback", "EVENTROUTER")
    w.hook_timer(3000, 0, 0, "reconnect_callback", "EVENTROUTER")
    w.hook_timer(1000 * 60 * 5, 0, 0, "slack_never_away_cb", "")

    w.hook_signal('buffer_closing', "buffer_closing_callback", "EVENTROUTER")
    w.hook_signal('buffer_switch', "buffer_switch_callback", "EVENTROUTER")
    w.hook_signal('window_switch', "buffer_switch_callback", "EVENTROUTER")
    w.hook_signal('quit', "quit_notification_cb", "")
    w.hook_signal('input_text_changed', "typing_notification_cb", "")

    w.hook_command(
        # Command name and description
        'slack', 'Plugin to allow typing notification and sync of read markers for slack.com',
        # Usage
        '[command] [command options]',
        # Description of arguments
        'Commands:\n' +
        '\n'.join(cmds.keys()) +
        '\nUse /slack help [command] to find out more\n',
        # Completions
        '|'.join(cmds.keys()),
        # Function name
        'slack_command_cb', '')
    # w.hook_command('me', '', 'stuff', 'stuff2', '', 'me_command_cb', '')

    w.hook_command_run('/me', 'me_command_cb', '')
    w.hook_command_run('/query', 'command_talk', '')
    w.hook_command_run('/join', 'command_talk', '')
    w.hook_command_run('/part', 'part_command_cb', '')
    w.hook_command_run('/leave', 'part_command_cb', '')
    w.hook_command_run('/topic', 'command_topic', '')
    w.hook_command_run('/thread', 'thread_command_callback', '')
    w.hook_command_run('/reply', 'thread_command_callback', '')
    w.hook_command_run('/rehistory', 'rehistory_command_callback', '')
    w.hook_command_run('/hide', 'hide_command_callback', '')
    w.hook_command_run('/msg', 'msg_command_cb', '')
    w.hook_command_run('/label', 'label_command_cb', '')
    w.hook_command_run("/input complete_next", "complete_next_cb", "")
    w.hook_command_run('/away', 'away_command_cb', '')

    w.hook_completion("nicks", "complete @-nicks for slack", "nick_completion_cb", "")
    w.hook_completion("emoji", "complete :emoji: for slack", "emoji_completion_cb", "")

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
    # return
    if level >= config.debug_level:
        global debug_string
        message = "DEBUG: {}".format(message)
        if fout:
            file('/tmp/debug.log', 'a+').writelines(message + '\n')
        if main_buffer:
                # w.prnt("", "---------")
                w.prnt("", "slack: " + message)
        else:
            if slack_debug and (not debug_string or debug_string in message):
                # w.prnt(slack_debug, "---------")
                w.prnt(slack_debug, message)

###### Config code


class PluginConfig(object):
    # Default settings.
    # These are in the (string) format that weechat expects; at __init__ time
    # this value will be used to set the default for any settings not already
    # defined, and then the real (python) values of the settings will be
    # extracted.
    # TODO: setting descriptions.
    settings = {
        'colorize_private_chats': 'false',
        'debug_mode': 'false',
        'debug_level': '3',
        'distracting_channels': '',
        'show_reaction_nicks': 'false',
        'slack_api_token': 'INSERT VALID KEY HERE!',
        'slack_timeout': '20000',
        'switch_buffer_on_join': 'true',
        'trigger_value': 'false',
        'unfurl_ignore_alt_text': 'false',
        'record_events': 'false',
        'thread_suffix_color': 'lightcyan',
        'unhide_buffers_with_activity': 'false',
        'short_buffer_names': 'false',
        'channel_name_typing_indicator': 'true',
        'background_load_all_history': 'false',
        'never_away': 'false',
        'server_aliases': '',
    }

    # Set missing settings to their defaults. Load non-missing settings from
    # weechat configs.
    def __init__(self):
        self.migrate()
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

    def get_thread_suffix_color(self, key):
        return w.config_get_plugin("thread_suffix_color")

    def get_debug_level(self, key):
        return int(w.config_get_plugin(key))

    def get_slack_timeout(self, key):
        return int(w.config_get_plugin(key))

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
    print >> f, 'Call to %s on line %s of %s from line %s of %s' % \
        (func_name, func_line_no, func_filename,
         caller_line_no, caller_filename)
    f.flush()
    return


# Main
if __name__ == "__main__":

    w = WeechatWrapper(weechat)

    if w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE,
                  SCRIPT_DESC, "script_unloaded", ""):

        version = w.info_get("version_number", "") or 0
        if int(version) < 0x1030000:
            w.prnt("", "\nERROR: Weechat version 1.3+ is required to use {}.\n\n".format(SCRIPT_NAME))
        else:

            global EVENTROUTER
            EVENTROUTER = EventRouter()
            # setup_trace()

            # WEECHAT_HOME = w.info_get("weechat_dir", "")
            # STOP_TALKING_TO_SLACK = False

            # Global var section
            slack_debug = None
            config = PluginConfig()
            config_changed_cb = config.config_changed

            typing_timer = time.time()
            # domain = None
            # previous_buffer = None
            # slack_buffer = None

            # never_away = False
            hide_distractions = False
            # hotlist = w.infolist_get("hotlist", "", "")
            # main_weechat_buffer = w.info_get("irc_buffer", "{}.{}".format(domain, "DOESNOTEXIST!@#$"))

            w.hook_config("plugins.var.python." + SCRIPT_NAME + ".*", "config_changed_cb", "")

            load_emoji()
            setup_hooks()

            # attach to the weechat hooks we need

            tokens = config.slack_api_token.split(',')
            for t in tokens:
                s = SlackRequest(t, 'rtm.start', {})
                EVENTROUTER.receive(s)
            if config.record_events:
                EVENTROUTER.record()
            EVENTROUTER.handle_next()
            w.hook_timer(10, 0, 0, "handle_next", "")
            # END attach to the weechat hooks we need

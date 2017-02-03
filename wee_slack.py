# -*- coding: utf-8 -*-
#

import time
import json
import pickle
import sha
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
    import weechat as w
except:
    pass

SCRIPT_NAME = "slack_extension"
SCRIPT_AUTHOR = "Ryan Huber <rhuber@gmail.com>"
SCRIPT_VERSION = "1.99"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Extends weechat for typing notification/search/etc on slack.com"

BACKLOG_SIZE = 200
SCROLLBACK_SIZE = 500

CACHE_VERSION = "4"

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

NICK_GROUP_HERE = "0|Here"
NICK_GROUP_AWAY = "1|Away"

sslopt_ca_certs = {}
if hasattr(ssl, "get_default_verify_paths") and callable(ssl.get_default_verify_paths):
    ssl_defaults = ssl.get_default_verify_paths()
    if ssl_defaults.cafile is not None:
        sslopt_ca_certs = {'ca_certs': ssl_defaults.cafile}

##### BEGIN NEW

IGNORED_EVENTS = [
    "reconnect_url",
    "hello",
    "pref_change",
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
            import os
            if not os.path.exists(RECORD_DIR):
                os.makedirs(RECORD_DIR)

    def record_event(self, message_json, file_name_field):
        """
        complete
        Called each time you want to record an event.
        message_json is a json in dict form
        file_name_field is the json key whose value you want to be part of the file name
        """
        now = time.time()
        mtype = message_json.get(file_name_field, 'unknown')
        f = open('{}/{}-{}.json'.format(RECORD_DIR, now, mtype), 'w')
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
        return identifier

    def retrieve_context(self, identifier):
        """
        A place to retrieve data and vars needed by callback returns. We need this because
        weechat's "callback_data" has a limited size and weechat will crash if you exceed
        this size.
        """
        data = self.context.get(identifier, None)
        if data:
            return data

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
            data = self.teams[team_hash].ws.recv()
            message_json = json.loads(data)
            metadata = WeeSlackMetadata({
                "team": team_hash,
            }).jsonify()
            message_json["wee_slack_metadata"] = metadata
            if self.recording:
                self.record_event(message_json, 'type')
            self.receive_json(json.dumps(message_json))
        except WebSocketConnectionClosedException:
            #TODO: handle reconnect here
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
        dbg("RECEIVED CALLBACK with request of {} id of {} and  code {} of length {}".format(request_metadata.request, request_metadata.response_id, return_code, len(out)))
        if return_code == 0:
            if request_metadata.response_id in self.reply_buffer:
                self.reply_buffer[request_metadata.response_id] += out
            else:
                self.reply_buffer[request_metadata.response_id] = ""
                self.reply_buffer[request_metadata.response_id] += out
            try:
                j = json.loads(self.reply_buffer[request_metadata.response_id])
                j["wee_slack_process_method"] = request_metadata.request_normalized
                j["wee_slack_request_metadata"] = pickle.dumps(request_metadata)
                self.reply_buffer.pop(request_metadata.response_id)
                if self.recording:
                    self.record_event(j, 'wee_slack_process_method')
                self.receive_json(json.dumps(j))
                self.delete_context(data)
            except:
                dbg("HTTP REQUEST CALLBACK FAILED", True)
                pass
        elif return_code != -1:
            self.reply_buffer.pop(request_metadata.response_id, None)
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
    def handle_next(self):
        """
        complete
        Main handler of the EventRouter. This is called repeatedly
        via callback to drain events from the queue. It also attaches
        useful metadata and context to events as they are processed.
        """
        if len(self.queue) > 0:
            j = self.queue.pop(0)
            # Reply is a special case of a json reply from websocket.
            kwargs = {}
            if isinstance(j, SlackRequest):
                if j.should_try():
                    local_process_async_slack_api_request(j, self)
                    return

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
                    if isinstance(meta, str):
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
        if isinstance(buffer_ptr, str):
            self.buffers[buffer_ptr] = channel
        else:
            raise InvalidType(type(buffer_ptr))
    def unregister_buffer(self, buffer_ptr, update_remote=False, close_buffer=False):
        """
        complete
        Adds a weechat buffer to the list of handled buffers for this EventRouter
        """
        if isinstance(buffer_ptr, str):
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
        params = {'useragent': 'wee_slack {}'.format(SCRIPT_VERSION)}
        request.tried()
        context = event_router.store_context(request)
        w.hook_process_hashtable(weechat_request, params, config.slack_timeout, "receive_httprequest_callback", context)

###### New Callbacks

def receive_httprequest_callback(data, command, return_code, out, err):
    """
    complete
    This is a dirty hack. There must be a better way.
    """
    #def url_processor_cb(data, command, return_code, out, err):
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

def buffer_closing_callback(signal, sig_type, data):
    """
    complete
    Receives a callback from weechat when a buffer is being closed.
    We pass the eventrouter variable name in as a string, as
    that is the only way we can do dependency injection via weechat
    callback, hence the eval.
    """
    eval(signal).weechat_controller.unregister_buffer(data, True, False)
    return w.WEECHAT_RC_OK

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
        return w.WEECHAT_RC_OK_EAT

    reaction = re.match("^\s*(\d*)(\+|-):(.*):\s*$", data)
    if reaction:
        if reaction.group(2) == "+":
            channel.send_add_reaction(int(reaction.group(1) or 1), reaction.group(3))
        elif reaction.group(2) == "-":
            channel.send_remove_reaction(int(reaction.group(1) or 1), reaction.group(3))
#    elif data.startswith('s/'):
#        try:
#            old, new, flags = re.split(r'(?<!\\)/', data)[1:]
#        except ValueError:
#            pass
#        else:
#            # Replacement string in re.sub() is a string, not a regex, so get
#            # rid of escapes.
#            new = new.replace(r'\/', '/')
#            old = old.replace(r'\/', '/')
#            channel.change_previous_message(old.decode("utf-8"), new.decode("utf-8"), flags)
    else:
        channel.send_message(data)
        # channel.buffer_prnt(channel.server.nick, data)
#    channel.mark_read(True)
    return w.WEECHAT_RC_ERROR

def buffer_switch_callback(signal, sig_type, data):
    """
    incomplete
    Every time we change channels in weechat, we call this to:
    1) set read marker 2) determine if we have already populated
    channel history data
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
    eventrouter = eval(data)
    #global buffer_list_update

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
        self.domain = 'api.slack.com'
        self.request = request
        self.request_normalized = re.sub(r'\W+', '', request)
        self.token = token
        post_data["token"] = token
        self.post_data = post_data
        self.params = {'useragent': 'wee_slack {}'.format(SCRIPT_VERSION)}
        self.url = 'https://{}/api/{}?{}'.format(self.domain, request, urllib.urlencode(post_data))
        self.response_id = sha.sha("{}{}".format(self.url, time.time())).hexdigest()
#    def __repr__(self):
#        return "URL: {} Tries: {} ID: {}".format(self.url, self.tries, self.response_id)
    def request_string(self):
        return "{}".format(self.url)
    def tried(self):
        self.tries += 1
    def should_try(self):
        return self.tries < 3

class SlackTeam(object):
    """
    incomplete
    Team object under which users and channels live.. Does lots.
    """
    def __init__(self, eventrouter, token, team, nick, myidentifier, users, bots, channels):
        self.connected = False
        self.ws = None
        self.ws_counter = 0
        self.ws_replies = {}
        self.eventrouter = eventrouter
        self.token = token
        self.team = team
        self.domain = team + ".slack.com"
        self.nick = nick
        self.myidentifier = myidentifier
        self.channels = channels
        self.users = users
        self.bots = bots
        self.team_hash = str(sha.sha("{}{}".format(self.nick, self.team)).hexdigest())
        self.name = self.domain
        self.server_buffer = None
        self.got_history = True
        self.create_buffer()
        for c in self.channels.keys():
            channels[c].set_related_server(self)
            channels[c].open_if_we_should()
        #    self.channel_set_related_server(c)
        # Last step is to make sure my nickname is the set color
        self.users[self.myidentifier].force_color(w.config_string(w.config_get('weechat.color.chat_nick_self')))
    def __eq__(self, compare_str):
        if compare_str == self.token:
            return True
        else:
            return False
    def add_channel(self, channel):
        self.channels[channel["id"]] = channel
        channel.set_related_server(self)
#    def connect_request_generate(self):
#        return SlackRequest(self.token, 'rtm.start', {})
    def create_buffer(self):
        if not self.server_buffer:
            self.server_buffer = w.buffer_new("{}".format(self.domain), "buffer_input_callback", "EVENTROUTER", "", "")
            self.eventrouter.weechat_controller.register_buffer(self.server_buffer, self)
            if w.config_string(w.config_get('irc.look.server_buffer')) == 'merge_with_core':
                w.buffer_merge(self.server_buffer, w.buffer_search_main())
            w.buffer_set(self.server_buffer, "nicklist", "1")
    def buffer_prnt(self, data):
        w.prnt_date_tags(self.server_buffer, SlackTS().major, tag("backlog"), data)
    def get_channel_map(self):
        return {v.slack_name: k for k, v in self.channels.iteritems()}
    def get_username_map(self):
        return {v.name: k for k, v in self.users.iteritems()}
    def get_team_hash(self):
        return self.team_hash
    def refresh(self):
        self.rename()
    def rename(self):
        pass
    def attach_websocket(self, ws):
        self.ws = ws
    def is_user_present(self, user_id):
        user = self.users.get(user_id)
        if user.presence == 'active':
            return True
        else:
            return False
    def mark_read(self):
        pass
    def set_connected(self):
        self.connected = True
    def set_disconnected(self):
        self.connected = False
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
            self.ws.send(message)
            dbg("Sent {}...".format(message[:100]))
        except:
            dbg("Unexpected error: {}\nSent: {}".format(sys.exc_info()[0], data))
            self.connected = False

class SlackChannel(object):
    """
    Represents an individual slack channel.
    """
    def __init__(self, eventrouter, **kwargs):
        # We require these two things for a vaid object,
        # the rest we can just learn from slack
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.eventrouter = eventrouter
        self.slack_name = kwargs["name"]
        self.identifier = kwargs["id"]
        self.last_read = SlackTS(kwargs.get("last_read", SlackTS()))
        #print self.last_read
        self.channel_buffer = None
        self.team = None
        self.got_history = False
        self.messages = {}
        self.new_messages = False
        self.typing = {}
        self.type = 'channel'
        self.set_name(self.slack_name)
        #short name relates to the localvar we change for typing indication
        self.current_short_name = self.name
    def __repr__(self):
        return "Name:{} Identifier:{}".format(self.name, self.identifier)
    def set_name(self, slack_name):
        self.name = "#" + slack_name
    def refresh(self):
        return self.rename()
    def rename(self):
        if self.channel_buffer:
            if self.is_someone_typing():
                new_name = ">{}".format(self.formatted_name()[1:])
            else:
                new_name = self.formatted_name()
            if self.current_short_name != new_name:
                self.current_short_name = new_name
                w.buffer_set(self.channel_buffer, "short_name", new_name)
                return True
        return False
    def formatted_name(self):
        return self.name
    def update_from_message_json(self, message_json):
        for key, value in message_json.items():
            setattr(self, key, value)
    def open_if_we_should(self, force=False):
        try:
            if self.is_archived:
                return
        except:
            pass
        if force:
            self.create_buffer()
        else:
            for reason in ["is_member", "is_open", "unread_count"]:
                try:
                    if eval("self." + reason):
                        self.create_buffer()
                except:
                    pass
    def set_related_server(self, team):
        self.team = team
    def create_buffer(self):
        """
        incomplete
        Creates the weechat buffer where the channel magic happens.
        """
        if not self.channel_buffer:
            self.channel_buffer = w.buffer_new("{}.{}".format(self.team.domain, self.name), "buffer_input_callback", "EVENTROUTER", "", "")
            self.eventrouter.weechat_controller.register_buffer(self.channel_buffer, self)
            if self.type == "im":
                w.buffer_set(self.channel_buffer, "localvar_set_type", 'private')
            else:
                w.buffer_set(self.channel_buffer, "localvar_set_type", 'channel')
            w.buffer_set(self.channel_buffer, "localvar_set_channel", self.name)
            w.buffer_set(self.channel_buffer, "short_name", self.formatted_name())
            if self.server.alias:
                w.buffer_set(self.channel_buffer, "localvar_set_server", self.server.alias)
            else:
                w.buffer_set(self.channel_buffer, "localvar_set_server", self.server.team)
            self.eventrouter.weechat_controller.set_refresh_buffer_list(True)
        if self.unread_count != 0 and not self.muted:
            w.buffer_set(self.channel_buffer, "hotlist", "1")
    def destroy_buffer(self, update_remote):
        if self.channel_buffer is not None:
            self.channel_buffer = None
        self.got_history = False
        #if update_remote and not eventrouter.shutting_down:
        if update_remote and not self.eventrouter.shutting_down:
            s = SlackRequest(self.team.token, SLACK_API_TRANSLATOR[self.type]["leave"], {"channel": self.identifier}, team_hash=self.team.team_hash, channel_identifier=self.identifier)
            EVENTROUTER.receive(s)
    def buffer_prnt(self, nick, text, timestamp, **kwargs):
        data = "{}\t{}".format(nick, text)
        ts = SlackTS(timestamp)
        if self.channel_buffer:
            #backlog messages - we will update the read marker as we print these
            backlog = False
            if ts <= SlackTS(self.last_read):
                tags = tag("backlog")
                backlog = True
            elif self.type in ["im", "mpdm"]:
                tags = tag("dm")
                self.new_messages = True
            else:
                tags = tag("default")
                self.new_messages = True

            w.prnt_date_tags(self.channel_buffer, ts.major, tags, data)
            modify_print_time(self.channel_buffer, ts.minorstr(), ts.major)
            if backlog:
                self.mark_read(ts, update_remote=False, force=True)
    def send_message(self, message):
        #team = self.eventrouter.teams[self.team]
        message = linkify_text(message, self.team, self)
        dbg(message)
        request = {"type": "message", "channel": self.identifier, "text": message, "_team": self.team.team_hash, "user": self.team.myidentifier}
        self.team.send_to_websocket(request)
        self.mark_read(force=True)
    def store_message(self, message, team, from_me=False):
        if from_me:
            message.message_json["user"] = team.myidentifier
        self.messages[SlackTS(message.ts)] = message
        if len(self.messages.keys()) > SCROLLBACK_SIZE:
            mk = self.messages.keys()
            mk.sort()
            for k in mk[:SCROLLBACK_SIZE]:
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
    def is_visible(self):
        return w.buffer_get_integer(self.channel_buffer, "hidden") == 0
    def get_history(self):
        #if config.cache_messages:
        #    for message in message_cache[self.identifier]:
        #        process_message(json.loads(message), True)
        s = SlackRequest(self.team.token, SLACK_API_TRANSLATOR[self.type]["history"], {"channel": self.identifier, "count": BACKLOG_SIZE}, team_hash=self.team.team_hash, channel_identifier=self.identifier)
        EVENTROUTER.receive(s)
        #async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["history"], {"channel": self.identifier, "count": BACKLOG_SIZE})
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
        return sorted(self.messages)
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
        #self.name = self.formatted_name(" ")
    def set_name(self, slack_name):
        self.name = slack_name
    def create_buffer(self):
        if not self.channel_buffer:
            super(SlackDMChannel, self).create_buffer()
            w.buffer_set(self.channel_buffer, "localvar_set_type", 'private')
    def update_color(self):
        if config.colorize_private_chats:
            self.color_name = w.info_get('irc_nick_color_name', self.name.encode('utf-8'))
            self.color = w.color(self.color_name)
        else:
            self.color = ""
            self.color_name = ""
    def formatted_name(self, prepend="", enable_color=True):
        if config.colorize_private_chats and enable_color:
            print_color = self.color
        else:
            print_color = ""
        return print_color + prepend + self.name

    def refresh(self):
        return self.rename()

    def rename(self):
        if self.channel_buffer:
            if self.team.is_user_present(self.user):
                new_name = "+{}".format(self.formatted_name())
            else:
                new_name = " {}".format(self.formatted_name())
            if self.current_short_name != new_name:
                self.current_short_name = new_name
                w.buffer_set(self.channel_buffer, "short_name", new_name)
                return True
        return False


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

class SlackMPDMChannel(SlackChannel):
    """
    An MPDM channel is a special instance of a 'group' channel.
    We change the name to look less terrible in weechat.
    """
    def __init__(self, eventrouter, **kwargs):
        super(SlackMPDMChannel, self).__init__(eventrouter, **kwargs)
        n = kwargs.get('name')
        self.set_name(n)
    def set_name(self, n):
        self.name = "|".join("-".join(n.split("-")[1:-1]).split("--"))
        self.type = "group"
    def rename(self):
        pass

class SlackUser(object):
    """
    Represends an individual slack user. Also where you set their name formatting.
    """
    def __init__(self, **kwargs):
        # We require these two things for a vaid object,
        # the rest we can just learn from slack
        self.identifier = kwargs["id"]
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
        if config.colorize_nicks:
            self.color_name = w.info_get('irc_nick_color_name', self.name.encode('utf-8'))
            self.color = w.color(self.color_name)
        else:
            self.color = ""
            self.color_name = ""
    def formatted_name(self, prepend="", enable_color=True):
        if config.colorize_nicks and enable_color:
            print_color = self.color
        else:
            print_color = ""
        return print_color + prepend + self.name

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
    """
    def __init__(self, message_json, team, channel):
        self.team = team
        self.channel = channel
        self.message_json = message_json
        self.sender = self.get_sender()
        self.suffix = ''
        self.ts = SlackTS(message_json['ts'])
    def render(self, force=False):
        return render(self.message_json, self.team, self.channel, force) + self.suffix
    def change_text(self, new_text):
        self.message_json["text"] = new_text
        dbg(self.message_json)
    def change_suffix(self, new_suffix):
        self.suffix = new_suffix
        dbg(self.message_json)
    def get_sender(self, utf8=True):
        name = u""
        if 'bot_id' in self.message_json and self.message_json['bot_id'] is not None:
            name = u"{} :]".format(self.team.bots[self.message_json["bot_id"]].formatted_name())
        elif 'user' in self.message_json:
            if self.message_json['user'] == self.team.myidentifier:
                name = self.team.users[self.team.myidentifier].name
            elif self.message_json['user'] in self.team.users:
                u = self.team.users[self.message_json['user']]
                if u.is_bot:
                    name = u"{} :]".format(u.formatted_name())
                else:
                    name = u"{}".format(u.formatted_name())
        elif 'username' in self.message_json:
            name = u"-{}-".format(self.message_json["username"])
        elif 'service_name' in self.message_json:
            name = u"-{}-".format(self.message_json["service_name"])
        else:
            name = u""
        if utf8:
            return name.encode('utf-8')
        else:
            return name
    def add_reaction(self, reaction, user):
        m = self.message_json.get('reactions', None)
        if m:
            found = False
            for r in m:
                if r["name"] == reaction and user not in r["users"]:
                    r["users"].append(user)
                    found = True
            if not found:
                self.message_json["reactions"].append({u"name": reaction, u"users": [user]})
        else:
            self.message_json["reactions"] = [{u"name": reaction, u"users": [user]}]
    def remove_reaction(self, reaction, user):
        m = self.message_json.get('reactions', None)
        if m:
            for r in m:
                if r["name"] == reaction and user in r["users"]:
                    r["users"].remove(user)
        else:
            pass


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

        users = {}
        for item in login_data["users"]:
            users[item["id"]] = SlackUser(**item)
            #users.append(SlackUser(**item))

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
            login_data["team"]["domain"],
            login_data["self"]["name"],
            login_data["self"]["id"],
            users,
            bots,
            channels,
        )
        eventrouter.register_team(t)

        web_socket_url = login_data['url']
        try:
            ws = create_connection(web_socket_url, sslopt=sslopt_ca_certs)
            w.hook_fd(ws.sock._sock.fileno(), 1, 0, 0, "receive_ws_callback", t.get_team_hash())
            #ws_hook = w.hook_fd(ws.sock._sock.fileno(), 1, 0, 0, "receive_ws_callback", pickle.dumps(t))
            ws.sock.setblocking(0)
            t.attach_websocket(ws)
            t.set_connected()
        except Exception as e:
            dbg("websocket connection error: {}".format(e))
            return False

        t.buffer_prnt('Connected to Slack')
        t.buffer_prnt('{:<20} {}'.format(u"Websocket URL", login_data["url"]))
        t.buffer_prnt('{:<20} {}'.format(u"User name", login_data["self"]["name"]))
        t.buffer_prnt('{:<20} {}'.format(u"User ID", login_data["self"]["id"]))
        t.buffer_prnt('{:<20} {}'.format(u"Team name", login_data["team"]["name"]))
        t.buffer_prnt('{:<20} {}'.format(u"Team domain", login_data["team"]["domain"]))
        t.buffer_prnt('{:<20} {}'.format(u"Team id", login_data["team"]["id"]))

        dbg("connected to {}".format(t.domain))

    #self.identifier = self.domain

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
    kwargs['output_type'] = "backlog"
    for message in reversed(message_json["messages"]):
        process_message(message, eventrouter, **kwargs)

###### New/converted process_ and subprocess_ methods

def process_manual_presence_change(message_json, eventrouter, **kwargs):
    process_presence_change(message_json, eventrouter, **kwargs)


def process_presence_change(message_json, eventrouter, **kwargs):
    kwargs["user"].presence = message_json["presence"]

def process_user_typing(message_json, eventrouter, **kwargs):
    channel = kwargs["channel"]
    team = kwargs["team"]
    if channel:
        channel.set_typing(team.users.get(message_json["user"]).name)

def process_pong(message_json, eventrouter, **kwargs):
    pass

def process_message(message_json, eventrouter, store=True, **kwargs):
    channel = kwargs["channel"]
    team = kwargs["team"]
    #try:
    # send these subtype messages elsewhere
    known_subtypes = [
        #'thread_message',
        #'message_replied',
        'message_changed',
        'message_deleted',
        #'channel_join',
        #'channel_leave',
        #'channel_topic',
        #'group_join',
        #'group_leave',
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
        #print text

        # special case with actions.
        if text.startswith("_") and text.endswith("_"):
            text = text[1:-1]
            if message.sender != channel.server.nick:
                text = message.sender + " " + text
            channel.buffer_prnt(w.prefix("action").rstrip(), text, message.ts, **kwargs)

        else:
            suffix = ''
            if 'edited' in message_json:
                suffix = ' (edited)'
            channel.buffer_prnt(message.sender, text + suffix, message.ts, **kwargs)

        if store:
            channel.store_message(message, team)
        dbg("NORMAL REPLY {}".format(message_json))

def subprocess_thread_message(message_json, eventrouter, channel, team):
    dbg("REPLIEDDDD: " + str(message_json))
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

    #if threadinfo[0]:
    #    channel.messages[threadinfo[1]].become_thread()
    #    message_json["item"]["ts"], message_json)
    #channel.change_message(message_json["thread_ts"], None, message_json["text"])
    #channel.become_thread(message_json["item"]["ts"], message_json)


def subprocess_message_changed(message_json, eventrouter, channel, team):
    m = message_json.get("message", None)
    if m:
        new_message = m
        #message = SlackMessage(new_message, team, channel)
        #if "attachments" in m:
        #    message_json["attachments"] = m["attachments"]
        #if "text" in m:
        #    if "text" in message_json:
        #        message_json["text"] += m["text"]
        #        dbg("added text!")
        #    else:
        #        message_json["text"] = m["text"]
        #if "fallback" in m:
        #    if "fallback" in message_json:
        #        message_json["fallback"] += m["fallback"]
        #    else:
        #        message_json["fallback"] = m["fallback"]

    text_before = (len(new_message['text']) > 0)
    new_message["text"] += unwrap_attachments(message_json, text_before)
    if "edited" in new_message:
        channel.change_message(new_message["ts"], new_message["text"], ' (edited)')
    else:
        channel.change_message(new_message["ts"], new_message["text"])

def subprocess_message_deleted(message_json, eventrouter, channel, team):
    channel.change_message(message_json["deleted_ts"], "(deleted)", '')

def process_reply(message_json, eventrouter, **kwargs):
    dbg('processing reply')
    #dbg(message_json, True)
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
    #    m = Message(message_json, server=server)
        #dbg(m, True)

        #if "type" in message_json:
        #    if message_json["type"] == "message" and "channel" in message_json.keys():
        #        message_json["ts"] = message_json["ts"]
        #        channels.find(message_json["channel"]).store_message(m, from_me=True)

        #        channels.find(message_json["channel"]).buffer_prnt(server.nick, m.render(), m.ts)
        process_message(m.message_json, eventrouter, channel=channel, team=team)
        dbg("REPLY {}".format(message_json))
    except KeyError:
        dbg("Unexpected reply {}".format(message_json))

def process_channel_marked(message_json, eventrouter, **kwargs):
    """
    complete
    """
    channel = kwargs["channel"]
    ts = kwargs["ts"]
    channel.mark_read(ts=ts, update_remote=False)
def process_group_marked(message_json, eventrouter, **kwargs):
    process_channel_marked(message_json, eventrouter, **kwargs)
def process_im_marked(message_json, eventrouter, **kwargs):
    process_channel_marked(message_json, eventrouter, **kwargs)
def process_mpim_marked(message_json, eventrouter, **kwargs):
    process_channel_marked(message_json, eventrouter, **kwargs)

def process_channel_joined(message_json, eventrouter, **kwargs):
    item = message_json["channel"]
    kwargs['team'].channels[item["id"]].update_from_message_json(item)
    kwargs['team'].channels[item["id"]].open_if_we_should()

def process_channel_created(message_json, eventrouter, **kwargs):
    item = message_json["channel"]
    c = SlackChannel(eventrouter, team=kwargs["team"], **item)
    kwargs['team'].channels[item["id"]] = c

def process_im_open(message_json, eventrouter, **kwargs):
    item = message_json
    kwargs['team'].channels[item["channel"]].open_if_we_should(True)

def process_im_close(message_json, eventrouter, **kwargs):
    item = message_json
    cbuf = kwargs['team'].channels[item["channel"]].channel_buffer
    eventrouter.weechat_controller.unregister_buffer(cbuf, False, True)

def process_reaction_added(message_json, eventrouter, **kwargs):
    channel = kwargs['team'].channels[message_json["item"]["channel"]]
    if message_json["item"].get("type") == "message":
        ts = message_json['item']["ts"]

        channel.messages[ts].add_reaction(message_json["reaction"], message_json["user"])
        channel.change_message(ts)
    else:
        dbg("reaction to item type not supported: " + str(message_json))

def process_reaction_removed(message_json, eventrouter, **kwargs):
    channel = kwargs['team'].channels[message_json["item"]["channel"]]
    if message_json["item"].get("type") == "message":
        ts = message_json['item']["ts"]

        channel.messages[ts].remove_reaction(message_json["reaction"], message_json["user"])
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
                text = u""
        else:
            text = u""

        text = unfurl_refs(text, ignore_alt_text=config.unfurl_ignore_alt_text)

        text_before = (len(text) > 0)
        text += unfurl_refs(unwrap_attachments(message_json, text_before), ignore_alt_text=config.unfurl_ignore_alt_text)

        text = text.lstrip()
        text = text.replace("\t", "    ")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&amp;", "&")
        text = text.encode('utf-8')

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
    message = message.split(' ')
    for item in enumerate(message):
        targets = re.match('.*([@#])([\w.-]+[\w. -])(\W*)', item[1])
        #print targets
        if targets and targets.groups()[0] == '@':
            #print targets.groups()
            named = targets.groups()
            if named[1] in ["group", "channel", "here"]:
                message[item[0]] = "<!{}>".format(named[1])
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

    #dbg(message)
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
            if id.startswith("#C") or id.startswith("@U"):
                display_text = ref.split('|')[1]
            else:
                url, desc = ref.split('|', 1)
                display_text = u"{} ({})".format(url, desc)
    else:
        display_text = resolve_ref(ref)
    return display_text

def unwrap_attachments(message_json, text_before):
    attachment_text = ''
    a = message_json.get("attachments", None)
    if a:
        if text_before:
            attachment_text = u'\n'
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
    #TODO: This hack to use eventrouter needs to go
    #this resolver should probably move to the slackteam or eventrouter itself
    #global EVENTROUTER
    if 'EVENTROUTER' in globals():
        e = EVENTROUTER
        if ref.startswith('@U') or ref.startswith('@W'):
            for t in e.teams.keys():
                if ref[1:] in e.teams[t].users:
                    #try:
                    return "@{}".format(e.teams[t].users[ref[1:]].name)
                    #except:
                    #    dbg("NAME: {}".format(ref))
        elif ref.startswith('#C'):
            for t in e.teams.keys():
                if ref[1:] in e.teams[t].channels:
                    #try:
                    return "{}".format(e.teams[t].channels[ref[1:]].name)
                    #except:
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

def tag(tagset, user="unknown user"):
    default_tag = "nick_" + user
    tagsets = {
        #when replaying something old
        "backlog": "no_highlight,notify_none,logger_backlog_end",
        #when posting messages to a muted channel
        "muted": "no_highlight,notify_none,logger_backlog_end",
        #when my nick is in the message
        "highlightme": "notify_highlight,log1",
        #when receiving a direct message
        "dm": "notify_private,notify_message,log1,irc_privmsg",
        #when this is a join/leave, attach for smart filter ala:
        #if user in [x.strip() for x in w.prefix("join"), w.prefix("quit")]
        "joinleave": "irc_smart_filter",
        #catchall ?
        "default": "notify_message,log1,irc_privmsg",
    }
    return default_tag + "," + tagsets[tagset]


###### New/converted command_ commands

def slack_command_cb(data, current_buffer, args):
    a = args.split(' ', 1)
    if len(a) > 1:
        function_name, args = a[0], " ".join(a[1:])
    else:
        function_name, args = a[0], None

    try:
        cmds[function_name](current_buffer, args)
    except KeyError:
        w.prnt("", "Command not found: " + function_name)
    return w.WEECHAT_RC_OK

def command_p(current_buffer, args):
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


##### END NEW


def dbg(message, main_buffer=False, fout=False):
    """
    send debug output to the slack-debug buffer and optionally write to a file.
    """
    #TODO: do this smarter
    #return
    global debug_string
    message = "DEBUG: {}".format(message)
    # message = message.encode('utf-8', 'replace')
    if fout:
        file('/tmp/debug.log', 'a+').writelines(message + '\n')
    if main_buffer:
            #w.prnt("", "---------")
            w.prnt("", "slack: " + message)
    else:
        if slack_debug and (not debug_string or debug_string in message):
            #w.prnt(slack_debug, "---------")
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
        'colorize_messages': 'false',
        'colorize_nicks': 'true',
        'colorize_private_chats': 'false',
        'debug_mode': 'false',
        'distracting_channels': '',
        'show_reaction_nicks': 'false',
        'slack_api_token': 'INSERT VALID KEY HERE!',
        'slack_timeout': '20000',
        'switch_buffer_on_join': 'true',
        'trigger_value': 'false',
        'unfurl_ignore_alt_text': 'false',
        'cache_messages': 'true',
        'record_events': 'false',
    }

    # Set missing settings to their defaults. Load non-missing settings from
    # weechat configs.
    def __init__(self):
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

    def get_slack_api_token(self, key):
        token = w.config_get_plugin("slack_api_token")
        if token.startswith('${sec.data'):
            return w.string_eval_expression(token, {}, {}, {})
        else:
            return token

    def get_slack_timeout(self, key):
        return int(w.config_get_plugin(key))


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

    if w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE,
                  SCRIPT_DESC, "script_unloaded", ""):

        version = w.info_get("version_number", "") or 0
        if int(version) < 0x1030000:
            w.prnt("", "\nERROR: Weechat version 1.3+ is required to use {}.\n\n".format(SCRIPT_NAME))
        else:

            #setup_trace()

            WEECHAT_HOME = w.info_get("weechat_dir", "")
            CACHE_NAME = "slack.cache"
            STOP_TALKING_TO_SLACK = False

            # Global var section
            slack_debug = None
            config = PluginConfig()
            config_changed_cb = config.config_changed

            typing_timer = time.time()
            domain = None
            previous_buffer = None
            slack_buffer = None

            never_away = False
            hide_distractions = False
            hotlist = w.infolist_get("hotlist", "", "")
            main_weechat_buffer = w.info_get("irc_buffer", "{}.{}".format(domain, "DOESNOTEXIST!@#$"))

            message_cache = collections.defaultdict(list)
            if config.cache_messages:
                cache_load()

            #servers = SearchList()
            #for token in config.slack_api_token.split(','):
            #    server = SlackServer(token)
            #    servers.append(server)
            #channels = SearchList()
            #users = SearchList()
            #threads = SearchList()

            w.hook_config("plugins.var.python." + SCRIPT_NAME + ".*", "config_changed_cb", "")
            #w.hook_timer(3000, 0, 0, "slack_connection_persistence_cb", "")

            # attach to the weechat hooks we need
            #w.hook_timer(1000, 0, 0, "typing_update_cb", "")
            w.hook_timer(1000, 0, 0, "buffer_list_update_callback", "EVENTROUTER")
            w.hook_timer(1000 * 60 * 29, 0, 0, "slack_never_away_cb", "")
            w.hook_timer(1000 * 60 * 5, 0, 0, "cache_write_cb", "")
            w.hook_signal('buffer_closing', "buffer_closing_callback", "EVENTROUTER")
            #w.hook_signal('buffer_opened', "buffer_opened_cb", "")
            w.hook_signal('buffer_switch', "buffer_switch_callback", "EVENTROUTER")
            w.hook_signal('window_switch', "buffer_switch_callback", "EVENTROUTER")
            #w.hook_signal('input_text_changed', "typing_notification_cb", "")
            w.hook_signal('quit', "quit_notification_cb", "")
            w.hook_signal('window_scrolled', "scrolled_cb", "")
            cmds = {k[8:]: v for k, v in globals().items() if k.startswith("command_")}
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
            w.hook_command('me', 'me_command_cb', '')
            w.hook_command('me', '', 'stuff', 'stuff2', '', 'me_command_cb', '')
            w.hook_command_run('/query', 'join_command_cb', '')
            w.hook_command_run('/join', 'join_command_cb', '')
            w.hook_command_run('/part', 'part_command_cb', '')
            w.hook_command_run('/leave', 'part_command_cb', '')
            w.hook_command_run('/topic', 'topic_command_cb', '')
            w.hook_command_run('/msg', 'msg_command_cb', '')
            w.hook_command_run('/label', 'label_command_cb', '')
            w.hook_command_run("/input complete_next", "complete_next_cb", "")
            w.hook_command_run('/away', 'away_command_cb', '')
            w.hook_completion("nicks", "complete @-nicks for slack",
                              "nick_completion_cb", "")
            #w.bar_item_new('slack_typing_notice', 'typing_bar_item_cb', '')

            tok = config.slack_api_token.split(',')[0]
            s = SlackRequest(tok, 'rtm.start', {})
            global EVENTROUTER
            EVENTROUTER = EventRouter()
            if config.record_events:
                EVENTROUTER.record()
            EVENTROUTER.receive(s)
            EVENTROUTER.handle_next()
            w.hook_timer(10, 0, 0, "handle_next", "")
            # END attach to the weechat hooks we need

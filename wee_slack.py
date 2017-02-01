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
#import random

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
]

###### New central Event router

class EventRouter(object):

    def __init__(self):
        self.queue = []
        self.teams = {}
        self.weechat_buffers = {}
        self.previous_buffer = ""
        self.reply_buffer = {}
        self.cmds = {k[8:]: v for k, v in globals().items() if k.startswith("command_")}
        self.proc = {k[8:]: v for k, v in globals().items() if k.startswith("process_")}
        self.handlers = {k[7:]: v for k, v in globals().items() if k.startswith("handle_")}
        self.local_proc = {k[14:]: v for k, v in globals().items() if k.startswith("local_process_")}

    def register_team(self, team):
        """
        Adds a team to the list of known teams for this EventRouter
        """
        if isinstance(team, SlackTeam):
            self.teams[team.get_team_hash()] = team
        else:
            raise InvalidType(type(team))

    def register_weechat_buffer(self, buffer_ptr, channel):
        """
        Adds a weechat buffer to the list of handled buffers for this EventRouter
        """
        if isinstance(buffer_ptr, str):
            self.weechat_buffers[buffer_ptr] = channel
        else:
            raise InvalidType(type(buffer_ptr))

    def unregister_weechat_buffer(self, buffer_ptr):
        """
        Adds a weechat buffer to the list of handled buffers for this EventRouter
        """
        if isinstance(buffer_ptr, str):
            try:
                self.weechat_buffers[buffer_ptr].destroy_buffer()
                del self.weechat_buffers[buffer_ptr]
            except:
                dbg("Tried to close unknown buffer")
        else:
            raise InvalidType(type(buffer_ptr))

    def receive_ws_callback(self, team_hash):
        """
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
                #"channels": self.teams[team_hash].channels,
                #"users": self.teams[team_hash].users,
            }).jsonify()
            #print self.teams[team_hash].domain
            message_json["wee_slack_metadata"] = metadata
            #print message_json
            self.receive_json(json.dumps(message_json))
        except WebSocketConnectionClosedException:
            #TODO: handle reconnect here
            self.teams[team_hash].set_disconnected()
            return w.WEECHAT_RC_OK
        except Exception:
            dbg("socket issue: {}\n".format(traceback.format_exc()))
            return w.WEECHAT_RC_OK

    def receive_httprequest_callback(self, data, command, return_code, out, err):
        #def url_processor_cb(data, command, return_code, out, err):
        request_metadata = pickle.loads(data)
        dbg("RECEIVED CALLBACK with request of {} id of {} and  code {} of length {}".format(request_metadata.request, request_metadata.response_id, return_code, len(out)), main_buffer=True)
        if return_code == 0:
            if request_metadata.response_id in self.reply_buffer:
                self.reply_buffer[request_metadata.response_id] += out
                #print self.reply_buffer[request_metadata.response_id]
            else:
                self.reply_buffer[request_metadata.response_id] = ""
                self.reply_buffer[request_metadata.response_id] += out
            try:
                j = json.loads(self.reply_buffer[request_metadata.response_id])
                j["wee_slack_process_method"] = request_metadata.request_normalized
                j["wee_slack_request_metadata"] = pickle.dumps(request_metadata)
                #print self.reply_buffer[request_metadata.response_id]
                self.reply_buffer.pop(request_metadata.response_id)
                self.receive_json(json.dumps(j))
            except:
                dbg("FAILED")
                pass
        elif return_code != -1:
            self.reply_buffer.pop(request_metadata.response_id, None)
        else:
            if request_metadata.response_id not in self.reply_buffer:
                self.reply_buffer[request_metadata.response_id] = ""
            self.reply_buffer[request_metadata.response_id] += out

    def receive_json(self, data):
        dbg("RECEIVED JSON")
        dbg(str(data))
        message_json = json.loads(data)
        dbg(message_json)
        #print message_json.keys()
        self.queue.append(message_json)
    def receive(self, dataobj):
        dbg("RECEIVED QUEUE", main_buffer=True)
        #dbg(str(len(dataobj)), main_buffer=True)
        self.queue.append(dataobj)
    def handle_next(self):
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
            if "wee_slack_metadata" in j:

                if isinstance(j["wee_slack_metadata"], str):
                    dbg("string of metadata")
                if "team" in j["wee_slack_metadata"]:
                    kwargs["team"] = self.teams[j["wee_slack_metadata"]["team"]]
                    if "user" in j:
                        kwargs["user"] = self.teams[j["wee_slack_metadata"]["team"]].users[j["user"]]
                    if "channel" in j:
                        kwargs["channel"] = self.teams[j["wee_slack_metadata"]["team"]].channels[j["channel"]]

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
    EVENTROUTER.handle_next()
    return w.WEECHAT_RC_OK

###### New Local Processors

def local_process_async_slack_api_request(request, event_router):
    """
    Sends an API request to Slack. You'll need to give this a well formed SlackRequest object.
    """
    weechat_request = 'url:{}'.format(request.request_string())
    params = {'useragent': 'wee_slack {}'.format(SCRIPT_VERSION)}
    request.tried()
    context = pickle.dumps(request)
    w.hook_process_hashtable(weechat_request, params, config.slack_timeout, "receive_httprequest_callback", context)

###### New Callbacks

def receive_httprequest_callback(data, command, return_code, out, err):
    """
    This is a dirty hack. There must be a better way.
    """
    #def url_processor_cb(data, command, return_code, out, err):
    EVENTROUTER.receive_httprequest_callback(data, command, return_code, out, err)
    return w.WEECHAT_RC_OK

def receive_ws_callback(*args):
    """
    The first arg is all we want here. It contains the team
    hash which is set when we _hook the descriptor.
    This is a dirty hack. There must be a better way.
    """
    EVENTROUTER.receive_ws_callback(args[0])
    return w.WEECHAT_RC_OK

def buffer_closing_callback(signal, sig_type, data):
    eval(signal).unregister_weechat_buffer(data)
    return w.WEECHAT_RC_OK

def buffer_input_callback(signal, buffer_ptr, data):
    eventrouter = eval(signal)

    dbg(signal, True)
    dbg(data, True)
    dbg(buffer_ptr, True)
    channel = eventrouter.weechat_buffers[buffer_ptr]
    print channel
    if not channel:
        return w.WEECHAT_RC_OK_EAT

#    reaction = re.match("^\s*(\d*)(\+|-):(.*):\s*$", data)
#    if reaction:
#        if reaction.group(2) == "+":
#            channel.send_add_reaction(int(reaction.group(1) or 1), reaction.group(3))
#        elif reaction.group(2) == "-":
#            channel.send_remove_reaction(int(reaction.group(1) or 1), reaction.group(3))
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
    eventrouter = eval(signal)

    # this is to see if we need to gray out things in the buffer list
    if eventrouter.previous_buffer in eventrouter.weechat_buffers:
        pass
        #channels.find(previous_buffer).mark_read()

    if data in eventrouter.weechat_buffers:
        new_channel = eventrouter.weechat_buffers[data]
        #if new_channel:
        if not new_channel.got_history:
            new_channel.get_history()

        eventrouter.previous_buffer = data
    return w.WEECHAT_RC_OK

##### New Classes

class SlackRequest(object):
    """
    Encapsulates a Slack api request. Valuable as an object that we can add to the queue and/or retry.
    """
    def __init__(self, token, request, post_data={}, **kwargs):
        print '================='
        for key, value in kwargs.items():
            setattr(self, key, value)
            print "{} {}".format(key, value)
        print '================='
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
    def __init__(self, token, team, nick, myidentifier, users, channels):
        self.connected = False
        self.ws = None
        self.ws_counter = 0
        self.ws_replies = {}
        self.token = token
        self.team = team
        self.domain = team + ".slack.com"
        self.nick = nick
        self.myidentifier = myidentifier
        self.channels = channels
        self.users = users
        self.team_hash = str(sha.sha("{}{}".format(self.nick, self.team)).hexdigest())
        for c in self.channels.keys():
            channels[c].set_related_server(self)
            channels[c].open_if_we_should()
        #    self.channel_set_related_server(c)
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
    def get_team_hash(self):
        return self.team_hash
    def attach_websocket(self, ws):
        self.ws = ws
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
        self.eventrouter = eventrouter
        self.identifier = kwargs["id"]
        self.name = kwargs["name"]
        self.channel_buffer = None
        self.team = None
        self.got_history = False
        self.messages = {}
        self.type = 'channel'
        for key, value in kwargs.items():
            setattr(self, key, value)
    def __repr__(self):
        return "Name:{} Identifier:{}".format(self.name, self.identifier)
    def open_if_we_should(self):
        for reason in ["is_member", "is_open", "unread_count"]:
            try:
                if eval("self." + reason):
                    self.create_buffer()
            except:
                pass
        pass
    def set_related_server(self, team):
        self.team = team
    def create_buffer(self):
        if not self.channel_buffer:
            print self.team
            self.channel_buffer = w.buffer_new("{}.{}".format(self.team.domain, self.name), "buffer_input_callback", "EVENTROUTER", "", "")
            self.eventrouter.register_weechat_buffer(self.channel_buffer, self)

            #dbg(self.channel_buffer, True)
            w.buffer_set(self.channel_buffer, "localvar_set_type", 'channel')
            w.buffer_set(self.channel_buffer, "localvar_set_channel", self.name)
            w.buffer_set(self.channel_buffer, "short_name", self.name)
#            if self.server.alias:
#                w.buffer_set(self.channel_buffer, "localvar_set_server", self.server.alias)
#            else:
#                w.buffer_set(self.channel_buffer, "localvar_set_server", self.server.team)
#            buffer_list_update_next()
#        if self.unread_count != 0 and not self.muted:
#            w.buffer_set(self.channel_buffer, "hotlist", "1")
    def destroy_buffer(self):
        if self.channel_buffer:
            self.channel_buffer = None
    def buffer_prnt(self, nick, text, timestamp, *args):
        if self.channel_buffer:
            w.prnt(self.channel_buffer, "{}\t{}".format(nick, text))
        #dbg("should buffer print {} {}".format(nick, text), True)
    def send_message(self, message):
        #team = self.eventrouter.teams[self.team]
        #message = self.linkify_text(message)
        dbg(message)
        print self.team
        request = {"type": "message", "channel": self.identifier, "text": message, "_team": self.team.team_hash, "user": self.team.myidentifier}
        dbg(request, True)
        self.team.send_to_websocket(request)
    def store_message(self, message, team, from_me=False):
        if from_me:
            message.message_json["user"] = team.myidentifier
        self.messages[message.ts] = message
        if len(self.messages.keys()) > SCROLLBACK_SIZE:
            mk = self.messages.keys()
            mk.sort()
            for k in mk[:SCROLLBACK_SIZE]:
                del self.messages[k]
    def change_message(self, ts, text=None, suffix=''):
        #print "should have changed"
        if ts in self.messages:
            m = self.messages[ts]
            m.change_text(text)
        #m = self.get_message(ts)
        #text = m[2].render(force=True)
        #timestamp, time_id = ts.split(".", 2)
        #timestamp = int(timestamp)
        #modify_buffer_line(self.channel_buffer, text + suffix, timestamp, time_id)
        return True
    def get_history(self):
        #if config.cache_messages:
        #    for message in message_cache[self.identifier]:
        #        process_message(json.loads(message), True)
        s = SlackRequest(self.team.token, SLACK_API_TRANSLATOR[self.type]["history"], {"channel": self.identifier, "count": BACKLOG_SIZE}, team_hash=self.team.team_hash, channel_identifier=self.identifier)
        EVENTROUTER.receive(s)
        #async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["history"], {"channel": self.identifier, "count": BACKLOG_SIZE})
        self.got_history = True
    def sorted_message_keys(self):
        return sorted(self.messages)


class SlackDMChannel(SlackChannel):
    def __init__(self, eventrouter, users, **kwargs):
        dmuser = kwargs["user"]
        kwargs["name"] = users[dmuser].name
        super(SlackDMChannel, self).__init__(eventrouter, **kwargs)
        self.type = 'im'
    def create_buffer(self):
        if not self.channel_buffer:
            super(SlackDMChannel, self).create_buffer()
            w.buffer_set(self.channel_buffer, "localvar_set_type", 'private')

class SlackGroupChannel(SlackChannel):
    def __init__(self, eventrouter, **kwargs):
        super(SlackGroupChannel, self).__init__(eventrouter, **kwargs)
        self.type = "group"

class SlackMPDMChannel(SlackChannel):
    """
    An MPDM channel is a special instance of a 'group' channel.
    We change the name to look less terrible in weechat.
    """
    def __init__(self, eventrouter, **kwargs):
        n = kwargs.get('name')
        name = "|".join("-".join(n.split("-")[1:-1]).split("--"))
        kwargs["name"] = name
        super(SlackMPDMChannel, self).__init__(eventrouter, **kwargs)
        self.type = "group"

class SlackUser(object):
    """
    Represends an individual slack user.
    """
    def __init__(self, **kwargs):
        # We require these two things for a vaid object,
        # the rest we can just learn from slack
        self.identifier = kwargs["id"]
        self.name = kwargs["name"]
        for key, value in kwargs.items():
            setattr(self, key, value)
    def __repr__(self):
        return "Name:{} Identifier:{}".format(self.name, self.identifier)
    def formatted_name(self, prepend="", enable_color=True):
        if config.colorize_nicks and enable_color:
            print_color = self.color
        else:
            print_color = ""
        return print_color + prepend + self.name

class SlackMessage(object):
    def __init__(self, message_json, team, channel):
        self.team = team
        self.channel = channel
        self.message_json = message_json
        self.sender = self.get_sender()
        self.ts = message_json['ts']
    def render(self):
        return render(self.message_json, self.team, self.channel)
    def change_text(self, new_text):
        dbg("should change text to {}".format(new_text), True)
        return "meh"
    def get_sender(self, utf8=True):
        if 'bot_id' in self.message_json and self.message_json['bot_id'] is not None:
            name = u"{} :]".format(self.server.bots.find(self.message_json["bot_id"]).formatted_name())
        elif 'user' in self.message_json:
            if self.message_json['user'] in self.team.users:
                u = self.team.users[self.message_json['user']]
            if u.is_bot:
                name = u"{} :]".format(u.formatted_name())
            else:
                name = u.name
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

class WeeSlackMetadata(object):
    def __init__(self, meta):
        self.meta = meta
    def jsonify(self):
        return self.meta

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
            metadata.token,
            login_data["team"]["domain"],
            login_data["self"]["name"],
            login_data["self"]["id"],
            users,
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
    for message in message_json["messages"]:
        process_message(message, eventrouter, **kwargs)

###### New/converted process_ and subprocess_ methods

def process_manual_presence_change(message_json, eventrouter, **kwargs):
    process_presence_change(message_json, eventrouter, **kwargs)


def process_presence_change(message_json, eventrouter, **kwargs):
    kwargs["user"].presence = message_json["presence"]


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
        #'message_changed',
        #'message_deleted',
        #'channel_join',
        #'channel_leave',
        #'channel_topic',
        #'group_join',
        #'group_leave',
    ]
    if "thread_ts" in message_json and "reply_count" not in message_json:
        message_json["subtype"] = "thread_message"
    if "subtype" in message_json:
        if message_json["subtype"] in known_subtypes:
            f = eval('subprocess_' + message_json["subtype"])
            f(message_json, eventrouter, channel, team)

    else:
        message = SlackMessage(message_json, team, channel)
        #message = Message(message_json, server=team, channel=channel)
        text = message.render()
        #print text

        # special case with actions.
        if text.startswith("_") and text.endswith("_"):
            text = text[1:-1]
            if message.sender != channel.server.nick:
                text = message.sender + " " + text
            channel.buffer_prnt(w.prefix("action").rstrip(), text, message.ts)

        else:
            suffix = ''
            if 'edited' in message_json:
                suffix = ' (edited)'
            channel.buffer_prnt(message.sender, text + suffix, message.ts)

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
    m = message_json["message"]
    if "message" in message_json:
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

    text_before = (len(m['text']) > 0)
    m["text"] += unwrap_attachments(message_json, text_before)
    if "edited" in m:
        channel.change_message(m["ts"], m["text"], ' (edited)')
    else:
        channel.change_message(m["ts"], m["text"])

def process_reply(message_json, eventrouter, **kwargs):
    dbg('processing reply')
    dbg(message_json, True)
    team = kwargs["team"]
    identifier = message_json["reply_to"]
    try:
        original_message_json = team.ws_replies[identifier]
        del team.ws_replies[identifier]
        if "ts" in message_json:
            original_message_json["ts"] = message_json["ts"]
        else:
            dbg("no reply ts {}".format(message_json))

        if "channel" in original_message_json:
            channel = team.channels[original_message_json["channel"]]
        m = SlackMessage(original_message_json, team, channel)
    #    m = Message(message_json, server=server)
        dbg(m, True)

        #if "type" in message_json:
        #    if message_json["type"] == "message" and "channel" in message_json.keys():
        #        message_json["ts"] = message_json["ts"]
        #        channels.find(message_json["channel"]).store_message(m, from_me=True)

        #        channels.find(message_json["channel"]).buffer_prnt(server.nick, m.render(), m.ts)
        process_message(m.message_json, eventrouter, channel=channel, team=team)
        dbg("REPLY {}".format(message_json))
    except KeyError:
        dbg("Unexpected reply")

def process_channel_marked(message_json, eventrouter, **kwargs):
    channel = kwargs["channel"]
    dbg(channel, True)
    #channel.mark_read(False)
    #w.buffer_set(channel.channel_buffer, "hotlist", "-1")

def process_channel_joined(message_json, eventrouter, **kwargs):
    print message_json
    print kwargs
#    server = servers.find(message_json["_server"])
#    channel = server.channels.find(message_json["channel"])
#    text = unfurl_refs(message_json["text"], ignore_alt_text=False)
#    channel.buffer_prnt(w.prefix("join").rstrip(), text, message_json["ts"])
#    channel.user_join(message_json["user"])


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

        if "reactions" in message_json:
            text += create_reaction_string(message_json["reactions"])
        message_json["_rendered_text"] = text

        return text

def linkify_text(message):
    message = message.split(' ')
    for item in enumerate(message):
        targets = re.match('.*([@#])([\w.]+\w)(\W*)', item[1])
        if targets and targets.groups()[0] == '@':
            named = targets.groups()
            if named[1] in ["group", "channel", "here"]:
                message[item[0]] = "<!{}>".format(named[1])
            if self.server.users.find(named[1]):
                message[item[0]] = "<@{}>{}".format(self.server.users.find(named[1]).identifier, named[2])
        if targets and targets.groups()[0] == '#':
            named = targets.groups()
            if self.server.channels.find(named[1]):
                message[item[0]] = "<#{}|{}>{}".format(self.server.channels.find(named[1]).identifier, named[1], named[2])
    dbg(message)
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
    if "attachments" in message_json:
        if text_before:
            attachment_text = u'\n'
        for attachment in message_json["attachments"]:
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
            if "title" in attachment:
                if 'title_link' in attachment:
                    t.append('%s%s (%s)' % (prepend_title_text, attachment["title"], attachment["title_link"],))
                else:
                    t.append(prepend_title_text + attachment["title"])
                prepend_title_text = ''
            elif "from_url" in attachment:
                t.append(attachment["from_url"])
            if "text" in attachment:
                tx = re.sub(r' *\n[\n ]+', '\n', attachment["text"])
                t.append(prepend_title_text + tx)
                prepend_title_text = ''
            if 'fields' in attachment:
                for f in attachment['fields']:
                    if f['title'] != '':
                        t.append('%s %s' % (f['title'], f['value'],))
                    else:
                        t.append(f['value'])
            if t == [] and "fallback" in attachment:
                t.append(attachment["fallback"])
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
            w.prnt("", "---------")
            w.prnt("", "slack: " + message)
    else:
        if slack_debug and (not debug_string or debug_string in message):
            w.prnt(slack_debug, "---------")
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


# Main
if __name__ == "__main__":

    if w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE,
                  SCRIPT_DESC, "script_unloaded", ""):

        version = w.info_get("version_number", "") or 0
        if int(version) < 0x1030000:
            w.prnt("", "\nERROR: Weechat version 1.3+ is required to use {}.\n\n".format(SCRIPT_NAME))
        else:

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

            buffer_list_update = False
            previous_buffer_list_update = 0

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
            #w.hook_timer(1000, 0, 0, "buffer_list_update_cb", "")
            w.hook_timer(1000 * 60 * 29, 0, 0, "slack_never_away_cb", "")
            w.hook_timer(1000 * 60 * 5, 0, 0, "cache_write_cb", "")
            w.hook_signal('buffer_closing', "buffer_closing_callback", "EVENTROUTER")
            w.hook_signal('buffer_opened', "buffer_opened_cb", "")
            w.hook_signal('buffer_switch', "buffer_switch_callback", "EVENTROUTER")
            w.hook_signal('window_switch', "buffer_switch_callback", "EVENTROUTER")
            #w.hook_signal('input_text_changed', "typing_notification_cb", "")
            w.hook_signal('quit', "quit_notification_cb", "")
            w.hook_signal('window_scrolled', "scrolled_cb", "")
            #w.hook_command(
            #    # Command name and description
            #    'slack', 'Plugin to allow typing notification and sync of read markers for slack.com',
            #    # Usage
            #    '[command] [command options]',
            #    # Description of arguments
            #    'Commands:\n' +
            #    '\n'.join(cmds.keys()) +
            #    '\nUse /slack help [command] to find out more\n',
            #    # Completions
            #    '|'.join(cmds.keys()),
            #    # Function name
            #    'slack_command_cb', '')
            # w.hook_command('me', 'me_command_cb', '')
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
            #async_slack_api_request("slack.com", self.token, "rtm.start", {"ts": t})
            #s = SlackRequest('xoxoxoxox', "blah.get", {"meh": "blah"})
            global EVENTROUTER
            EVENTROUTER = EventRouter()
            EVENTROUTER.receive(s)
            EVENTROUTER.handle_next()
            w.hook_timer(10, 0, 0, "handle_next", "")
            # END attach to the weechat hooks we need

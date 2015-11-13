# -*- coding: utf-8 -*-
#

from functools import wraps
import time
import json
import pickle
import sha
import re
import urllib
import HTMLParser
import sys
import traceback
from websocket import create_connection

# hack to make tests possible.. better way?
try:
    import weechat as w
except:
    pass

SCRIPT_NAME = "slack_extension"
SCRIPT_AUTHOR = "Ryan Huber <rhuber@gmail.com>"
SCRIPT_VERSION = "0.98.7"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Extends weechat for typing notification/search/etc on slack.com"

BACKLOG_SIZE = 200
SCROLLBACK_SIZE = 2000

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
        "leave": "im.close",
        "mark": "im.mark",
    },
    "group": {
        "history": "groups.history",
        "join": "channels.join",
        "leave": "groups.leave",
        "mark": "groups.mark",
    }

}

NICK_GROUP_HERE = "0|Here"
NICK_GROUP_AWAY = "1|Away"

def dbg(message, fout=False, main_buffer=False):
    """
    send debug output to the slack-debug buffer and optionally write to a file.
    """
    message = "DEBUG: {}".format(message)
    #message = message.encode('utf-8', 'replace')
    if fout:
        file('/tmp/debug.log', 'a+').writelines(message + '\n')
    if main_buffer:
            w.prnt("", message)
    else:
        if slack_debug is not None:
            w.prnt(slack_debug, message)


class SearchList(list):
    """
    A normal python list with some syntactic sugar for searchability
    """
    def __init__(self):
        self.hashtable = {}
        super(SearchList, self).__init__(self)

    def find(self, name):
        if name in self.hashtable.keys():
            return self.hashtable[name]
        #this is a fallback to __eq__ if the item isn't in the hashtable already
        if self.count(name) > 0:
            self.update_hashtable()
            return self[self.index(name)]

    def append(self, item, aliases=[]):
        super(SearchList, self).append(item)
        self.update_hashtable()

    def update_hashtable(self):
        for child in self:
            if hasattr(child, "get_aliases"):
                for alias in child.get_aliases():
                    if alias is not None:
                        self.hashtable[alias] = child

    def find_by_class(self, class_name):
        items = []
        for child in self:
            if child.__class__ == class_name:
                items.append(child)
        return items

    def find_by_class_deep(self, class_name, attribute):
        items = []
        for child in self:
            if child.__class__ == self.__class__:
                items += child.find_by_class_deep(class_name, attribute)
            else:
                items += (eval('child.' + attribute).find_by_class(class_name))
        return items


class SlackServer(object):
    """
    Root object used to represent connection and state of the connection to a slack group.
    """
    def __init__(self, token):
        self.nick = None
        self.name = None
        self.domain = None
        self.login_data = None
        self.buffer = None
        self.token = token
        self.ws = None
        self.ws_hook = None
        self.users = SearchList()
        self.bots = SearchList()
        self.channels = SearchList()
        self.connecting = False
        self.connected = False
        self.communication_counter = 0
        self.message_buffer = {}
        self.ping_hook = None

        self.identifier = None
        self.connect_to_slack()

    def __eq__(self, compare_str):
        if compare_str == self.identifier or compare_str == self.token or compare_str == self.buffer:
            return True
        else:
            return False

    def __str__(self):
        return "{}".format(self.identifier)

    def __repr__(self):
        return "{}".format(self.identifier)

    def add_user(self, user):
        self.users.append(user, user.get_aliases())
        users.append(user, user.get_aliases())

    def add_bot(self, bot):
        self.bots.append(bot)

    def add_channel(self, channel):
        self.channels.append(channel, channel.get_aliases())
        channels.append(channel, channel.get_aliases())

    def get_aliases(self):
        aliases = [self.identifier, self.token, self.buffer]
        return aliases

    def find(self, name, attribute):
        attribute = eval("self." + attribute)
        return attribute.find(name)

    def get_communication_id(self):
        if self.communication_counter > 999:
            self.communication_counter = 0
        self.communication_counter += 1
        return self.communication_counter

    def send_to_websocket(self, data, expect_reply=True):
        data["id"] = self.get_communication_id()
        message = json.dumps(data)
        try:
            if expect_reply:
                self.message_buffer[data["id"]] = data
            self.ws.send(message)
            dbg("Sent {}...".format(message[:100]))
        except:
            dbg("Unexpected error: {}\nSent: {}".format(sys.exc_info()[0], data))
            self.connected = False

    def ping(self):
        request = {"type": "ping"}
        self.send_to_websocket(request)

    def connect_to_slack(self):
        t = time.time()
        if not self.connecting:
            async_slack_api_request("slack.com", self.token, "rtm.start", {"ts": t})
            self.connecting = True

    def connected_to_slack(self, login_data):
        if login_data["ok"]:
            self.domain = login_data["team"]["domain"] + ".slack.com"
            dbg("connected to {}".format(self.domain))
            self.identifier = self.domain
            self.nick = login_data["self"]["name"]
            self.create_local_buffer()

            if self.create_slack_websocket(login_data):
                if self.ping_hook:
                    w.unhook(self.ping_hook)
                    self.communication_counter = 0
                self.ping_hook = w.hook_timer(1000 * 5, 0, 0, "slack_ping_cb", self.domain)
                if len(self.users) and 0 or len(self.channels) == 0:
                    self.create_slack_mappings(login_data)

                self.connected = True
                self.connecting = False

                self.print_connection_info(login_data)
                if len(self.message_buffer) > 0:
                    for message_id in self.message_buffer.keys():
                        if self.message_buffer[message_id]["type"] != 'ping':
                            resend = self.message_buffer.pop(message_id)
                            dbg("Resent failed message.")
                            self.send_to_websocket(resend)
                            #sleep to prevent being disconnected by websocket server
                            time.sleep(1)
                        else:
                            self.message_buffer.pop(message_id)
            return True
        else:
            w.prnt("", "\n!! slack.com login error: " + login_data["error"] + "\n Please check your API token with\n \"/set plugins.var.python.slack_extension.slack_api_token (token)\"\n\n ")
            self.connected = False

    def print_connection_info(self, login_data):
        self.buffer_prnt('Connected to Slack', backlog=True)
        self.buffer_prnt('{:<20} {}'.format("Websocket URL", login_data["url"]), backlog=True)
        self.buffer_prnt('{:<20} {}'.format("User name", login_data["self"]["name"]), backlog=True)
        self.buffer_prnt('{:<20} {}'.format("User ID", login_data["self"]["id"]), backlog=True)
        self.buffer_prnt('{:<20} {}'.format("Team name", login_data["team"]["name"]), backlog=True)
        self.buffer_prnt('{:<20} {}'.format("Team domain", login_data["team"]["domain"]), backlog=True)
        self.buffer_prnt('{:<20} {}'.format("Team id", login_data["team"]["id"]), backlog=True)

    def create_local_buffer(self):
        if not w.buffer_search("", self.domain):
            self.buffer = w.buffer_new(self.domain, "buffer_input_cb", "", "", "")
            w.buffer_set(self.buffer, "nicklist", "1")

            w.nicklist_add_group(self.buffer, '', NICK_GROUP_HERE, "weechat.color.nicklist_group", 1)
            w.nicklist_add_group(self.buffer, '', NICK_GROUP_AWAY, "weechat.color.nicklist_group", 1)

    def create_slack_websocket(self, data):
        web_socket_url = data['url']
        try:
            self.ws = create_connection(web_socket_url)
            self.ws_hook = w.hook_fd(self.ws.sock._sock.fileno(), 1, 0, 0, "slack_websocket_cb", self.identifier)
            self.ws.sock.setblocking(0)
            return True
        except Exception as e:
            print("websocket connection error: {}".format(e))
            return False

    def create_slack_mappings(self, data):

        for item in data["users"]:
            self.add_user(User(self, item["name"], item["id"], item["presence"], item["deleted"]))

        for item in data["bots"]:
            self.add_bot(Bot(self, item["name"], item["id"], item["deleted"]))

        for item in data["channels"]:
            if "last_read" not in item:
                item["last_read"] = 0
            if "members" not in item:
                item["members"] = []
            if "topic" not in item:
                item["topic"] = {}
                item["topic"]["value"] = ""
            if not item["is_archived"]:
                self.add_channel(Channel(self, item["name"], item["id"], item["is_member"], item["last_read"], "#", item["members"], item["topic"]["value"]))
        for item in data["groups"]:
            if "last_read" not in item:
                item["last_read"] = 0
            if not item["is_archived"]:
                self.add_channel(GroupChannel(self, item["name"], item["id"], item["is_open"], item["last_read"], "#", item["members"], item["topic"]["value"]))
        for item in data["ims"]:
            if "last_read" not in item:
                item["last_read"] = 0
            name = self.users.find(item["user"]).name
            self.add_channel(DmChannel(self, name, item["id"], item["is_open"], item["last_read"]))
        for item in data['self']['prefs']['muted_channels'].split(','):
            if item == '':
                continue
            self.channels.find(item).muted = True

        for item in self.channels:
            item.get_history()

    def buffer_prnt(self, message='no message', user="SYSTEM", backlog=False):
        message = message.encode('ascii', 'ignore')
        if backlog:
            tags = "no_highlight,notify_none,logger_backlog_end"
        else:
            tags = ""
        if self.buffer:
            w.prnt_date_tags(self.buffer, 0, tags, "{}\t{}".format(user, message))
        else:
            pass
            #w.prnt("", "%s\t%s" % (user, message))

def buffer_input_cb(b, buffer, data):
    if not data.startswith('s/') or data.startswith('+'):
        channel = channels.find(buffer)
        channel.send_message(data)
        #channel.buffer_prnt(channel.server.nick, data)
    elif data.count('/') == 3:
        old, new = data.split('/')[1:3]
        channel = channels.find(buffer)
        channel.change_previous_message(old, new)
    channel.mark_read(True)
    return w.WEECHAT_RC_ERROR


class Channel(object):
    """
    Represents a single channel and is the source of truth
    for channel <> weechat buffer
    """
    def __init__(self, server, name, identifier, active, last_read=0, prepend_name="", members=[], topic=""):
        self.name = prepend_name + name
        self.identifier = identifier
        self.active = active
        self.last_read = float(last_read)
        self.members = set(members)
        self.topic = topic

        self.members_table = {}
        self.channel_buffer = None
        self.type = "channel"
        self.server = server
        self.typing = {}
        self.opening = False
        self.last_received = None
        self.messages = []
        self.scrolling = False
        self.muted = False
        if active:
            self.create_buffer()
            self.attach_buffer()
            self.create_members_table()
            self.update_nicklist()
            self.set_topic(self.topic)
            buffer_list_update_next()

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name

    def __eq__(self, compare_str):
        if compare_str == self.fullname() or compare_str == self.name or compare_str == self.identifier or compare_str == self.name[1:] or (compare_str == self.channel_buffer and self.channel_buffer is not None):
            return True
        else:
            return False

    def get_aliases(self):
        aliases = [self.fullname(), self.name, self.identifier, self.name[1:], ]
        if self.channel_buffer is not None:
            aliases.append(self.channel_buffer)
        return aliases

    def create_members_table(self):
        for user in self.members:
            self.members_table[user] = self.server.users.find(user)

    def create_buffer(self):
        channel_buffer = w.buffer_search("", "{}.{}".format(self.server.domain, self.name))
        if channel_buffer:
            self.channel_buffer = channel_buffer
        else:
            self.channel_buffer = w.buffer_new("{}.{}".format(self.server.domain, self.name), "buffer_input_cb", self.name, "", "")
            if self.type == "im":
                w.buffer_set(self.channel_buffer, "localvar_set_type", 'private')
            else:
                w.buffer_set(self.channel_buffer, "localvar_set_type", 'channel')
            w.buffer_set(self.channel_buffer, "short_name", 'loading..')
            buffer_list_update_next()

    def attach_buffer(self):
        channel_buffer = w.buffer_search("", "{}.{}".format(self.server.domain, self.name))
        if channel_buffer != main_weechat_buffer:
            self.channel_buffer = channel_buffer
            w.buffer_set(self.channel_buffer, "localvar_set_nick", self.server.nick)
#            w.buffer_set(self.channel_buffer, "highlight_words", self.server.nick)
        else:
            self.channel_buffer = None

    def detach_buffer(self):
        if self.channel_buffer is not None:
            w.buffer_close(self.channel_buffer)
            self.channel_buffer = None

    def update_nicklist(self):
        if self.channel_buffer:
            w.buffer_set(self.channel_buffer, "nicklist", "1")
            w.nicklist_remove_all(self.channel_buffer)

            here = w.nicklist_add_group(self.channel_buffer,
                                        '', NICK_GROUP_HERE, "weechat.color.nicklist_group", 1)
            afk = w.nicklist_add_group(self.channel_buffer,
                                       '', NICK_GROUP_AWAY, "weechat.color.nicklist_group", 1)
            try:
                for user in self.members:
                    user = self.members_table[user]
                    if user.deleted:
                        continue
                    if user.presence == 'away':
                        w.nicklist_add_nick(self.channel_buffer, afk, user.name, user.color_name, "", "", 1)
                    else:
                        w.nicklist_add_nick(self.channel_buffer, here, user.name, user.color_name, "", "", 1)
            except Exception as e:
                dbg("DEBUG: {} {} {}".format(self.identifier, self.name, e))

    def fullname(self):
        return "{}.{}".format(self.server.domain, self.name)

    def has_user(self, name):
        return name in self.members

    def user_join(self, name):
        self.members.add(name)
        self.create_members_table()
        self.update_nicklist()

    def user_leave(self, name):
        if name in self.members:
            self.members.remove(name)
        self.create_members_table()
        self.update_nicklist()

    def set_active(self):
        self.active = True

    def set_inactive(self):
        self.active = False

    def set_typing(self, user):
        self.typing[user] = time.time()
        buffer_list_update_next()

    def unset_typing(self, user):
        try:
            del self.typing[user]
            buffer_list_update_next()
        except:
            pass

    def send_message(self, message):
        message = self.linkify_text(message)
        dbg(message)
        request = {"type": "message", "channel": self.identifier, "text": message, "myserver": self.server.domain}
        self.server.send_to_websocket(request)

    def linkify_text(self, message):
        message = message.split(' ')
        for item in enumerate(message):
            if item[1].startswith('@') and len(item[1]) > 1:
                named = re.match('.*[@#](\w+)(\W*)', item[1]).groups()
                if named[0] in ["group", "channel", "here"]:
                    message[item[0]] = "<!{}>".format(named[0])
                if self.server.users.find(named[0]):
                    message[item[0]] = "<@{}|{}>{}".format(self.server.users.find(named[0]).identifier, named[0], named[1])
            if item[1].startswith('#') and self.server.channels.find(item[1]):
                named = re.match('.*[@#](\w+)(\W*)', item[1]).groups()
                if self.server.channels.find(named[0]):
                    message[item[0]] = "<#{}|{}>{}".format(self.server.channels.find(named[0]).identifier, named[0], named[1])
        dbg(message)
        return " ".join(message)

    def set_topic(self, topic):
        topic = topic.encode('ascii', 'ignore')
        w.buffer_set(self.channel_buffer, "title", topic)

    def open(self, update_remote=True):
        self.opening = True
        self.create_buffer()
        self.active = True
        self.get_history()
        if "info" in SLACK_API_TRANSLATOR[self.type]:
            async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["info"], {"name": self.name.lstrip("#")})
        if update_remote:
            if "join" in SLACK_API_TRANSLATOR[self.type]:
                async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["join"], {"name": self.name.lstrip("#")})
        self.opening = False

    def close(self, update_remote=True):
        #remove from cache so messages don't reappear when reconnecting
        if self.active:
            self.active = False
            self.detach_buffer()
        if update_remote:
            t = time.time()
            async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["leave"], {"channel": self.identifier})

    def closed(self):
        self.channel_buffer = None
        self.last_received = None
        self.close()

    def is_someone_typing(self):
        for user in self.typing.keys():
            if self.typing[user] + 4 > time.time():
                return True
        if len(self.typing) > 0:
            self.typing = {}
            buffer_list_update_next()
        return False

    def get_typing_list(self):
        typing = []
        for user in self.typing.keys():
            if self.typing[user] + 4 > time.time():
                typing.append(user)
        return typing

    def mark_read(self, update_remote=True):
        t = time.time()

        if self.channel_buffer:
            w.buffer_set(self.channel_buffer, "unread", "")
        if update_remote:
            self.last_read = time.time()
            self.update_read_marker(self.last_read)

    def update_read_marker(self, time):
        async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["mark"], {"channel": self.identifier, "ts": time})

    def rename(self):
        if current_domain_name() != self.server.domain and channels_not_on_current_server_color:
            color = w.color(channels_not_on_current_server_color)
        else:
            color = ""
        if self.is_someone_typing():
            new_name = ">{}".format(self.name[1:])
        else:
            new_name = self.name
        if self.channel_buffer:
            if w.buffer_get_string(self.channel_buffer, "short_name") != (color + new_name):
                w.buffer_set(self.channel_buffer, "short_name", color + new_name)

# deprecated in favor of redrawing the entire buffer
#    def buffer_prnt_changed(self, user, text, time, append=""):
#        if self.channel_buffer:
#            if user:
#                if self.server.users.find(user):
#                    name = self.server.users.find(user).formatted_name()
#                else:
#                    name = user
#                name = name.decode('utf-8')
#                modify_buffer_line(self.channel_buffer, name, text, time, append)
#            else:
#                modify_buffer_line(self.channel_buffer, None, text, time, append)

    def buffer_prnt(self, user='unknown_user', message='no message', time=0):
        """
        writes output (message) to a buffer (channel)
        """
        set_read_marker = False
        time_float = float(time)
        if time_float != 0 and self.last_read >= time_float:
            tags = "no_highlight,notify_none,logger_backlog_end"
            set_read_marker = True
        elif message.find(self.server.nick.encode('utf-8')) > -1:
            tags = "notify_highlight"
        elif user != self.server.nick and self.name in self.server.users:
            tags = "notify_private,notify_message"
        elif self.muted:
            tags = "no_highlight,notify_none,logger_backlog_end"
        elif user in [x.strip() for x in w.prefix("join"), w.prefix("quit")]:
            tags = "irc_smart_filter"
        else:
            tags = "notify_message"
        #don't write these to local log files
        #tags += ",no_log"
        time_int = int(time_float)
        if self.channel_buffer:
            if self.server.users.find(user):
                name = self.server.users.find(user).formatted_name()
            else:
                name = user
            name = name.decode('utf-8')
            #colorize nicks in each line
            chat_color = w.config_string(w.config_get('weechat.color.chat'))
            if type(message) is not unicode:
              message = message.decode('UTF-8', 'replace')
            for user in self.server.users:
                if user.name in message:
                    message = user.name_regex.sub(
                        r'\1\2{}\3'.format(user.formatted_name() + w.color(chat_color)),
                        message)
            message = HTMLParser.HTMLParser().unescape(message)
            data = u"{}\t{}".format(name, message).encode('utf-8')
            w.prnt_date_tags(self.channel_buffer, time_int, tags, data)

            if set_read_marker:
                self.mark_read(False)
        else:
            self.open(False)
        self.last_received = time
        self.unset_typing(user)

    def buffer_redraw(self):
        if self.channel_buffer and not self.scrolling:
            w.buffer_clear(self.channel_buffer)
            self.messages.sort()
            for message in self.messages:
                process_message(message.message_json, False)

    def set_scrolling(self):
        self.scrolling = True

    def unset_scrolling(self):
        self.scrolling = False
        self.buffer_redraw()

    def has_message(self, ts):
        return self.messages.count(ts) > 0

    def change_message(self, ts, text):
        if self.has_message(ts):
            message_index = self.messages.index(ts)
            self.messages[message_index].change_text(text)
            self.buffer_redraw()
            return True

    def add_reaction(self, ts, reaction):
        if self.has_message(ts):
            message_index = self.messages.index(ts)
            self.messages[message_index].add_reaction(reaction)
            self.buffer_redraw()
            return True

    def remove_reaction(self, ts, reaction):
        if self.has_message(ts):
            message_index = self.messages.index(ts)
            self.messages[message_index].remove_reaction(reaction)
            self.buffer_redraw()
            return True

    def change_previous_message(self, old, new):
        message = self.my_last_message()
        if new == "" and old == "":
            async_slack_api_request(self.server.domain, self.server.token, 'chat.delete', {"channel": self.identifier, "ts": message['ts']})
        else:
            new_message = message["text"].replace(old, new)
            async_slack_api_request(self.server.domain, self.server.token, 'chat.update', {"channel": self.identifier, "ts": message['ts'], "text": new_message})

    def my_last_message(self):
        for message in reversed(self.messages):
            if "user" in message.message_json and "text" in message.message_json and message.message_json["user"] == self.server.users.find(self.server.nick).identifier:
                return message.message_json

    def cache_message(self, message_json, from_me=False):
        if from_me:
            message_json["user"] = self.server.users.find(self.server.nick).identifier
        self.messages.append(Message(message_json))
        if len(self.messages) > SCROLLBACK_SIZE:
            self.messages = self.messages[-SCROLLBACK_SIZE:]

    def get_history(self):
        if self.active:
            for message in cache_get(self.identifier):
                process_message(json.loads(message), True)
            if self.last_received != None:
                async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["history"], {"channel": self.identifier, "oldest": self.last_received, "count": BACKLOG_SIZE})
            else:
                async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["history"], {"channel": self.identifier, "count": BACKLOG_SIZE})


class GroupChannel(Channel):

    def __init__(self, server, name, identifier, active, last_read=0, prepend_name="", members=[], topic=""):
        super(GroupChannel, self).__init__(server, name, identifier, active, last_read, prepend_name, members, topic)
        self.type = "group"


class DmChannel(Channel):

    def __init__(self, server, name, identifier, active, last_read=0, prepend_name=""):
        super(DmChannel, self).__init__(server, name, identifier, active, last_read, prepend_name)
        self.type = "im"

    def rename(self):
        if current_domain_name() != self.server.domain and channels_not_on_current_server_color:
            force_color = w.color(channels_not_on_current_server_color)
        else:
            force_color = None

        if self.server.users.find(self.name).presence == "active":
            new_name = self.server.users.find(self.name).formatted_name('+', force_color)
        else:
            new_name = self.server.users.find(self.name).formatted_name(' ', force_color)

        if self.channel_buffer:
            w.buffer_set(self.channel_buffer, "short_name", new_name)

    def update_nicklist(self):
        pass

class User(object):

    def __init__(self, server, name, identifier, presence="away", deleted=False):
        self.server = server
        self.name = name
        self.identifier = identifier
        self.presence = presence
        self.deleted = deleted

        self.channel_buffer = w.info_get("irc_buffer", "{}.{}".format(domain, self.name))
        self.update_color()
        self.name_regex = re.compile(r"([\W]|\A)(@{0,1})" + self.name + "('s|[^'\w]|\Z)")

        if deleted:
            return
        if self.presence == 'away':
            ngroup = w.nicklist_search_group(server.buffer, "", NICK_GROUP_AWAY)
        else:
            ngroup = w.nicklist_search_group(server.buffer, "", NICK_GROUP_HERE)
        self.nicklist_pointer = w.nicklist_add_nick(server.buffer, ngroup, self.name, self.color_name, "", "", 1)
#        w.nicklist_add_nick(server.buffer, "", self.formatted_name(), "", "", "", 1)

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name

    def __eq__(self, compare_str):
        try:
            if compare_str == self.name or compare_str == "@" + self.name or compare_str == self.identifier:
                return True
            else:
                return False
        except:
            return False

    def get_aliases(self):
        return [self.name, "@" + self.name, self.identifier]

    def set_active(self):
        self.presence = "active"
        for channel in self.server.channels:
            if channel.has_user(self.identifier):
                channel.update_nicklist()
        w.nicklist_nick_set(self.server.buffer, self.nicklist_pointer, "visible", "1")
        buffer_list_update_next()

    def set_inactive(self):
        self.presence = "away"
        for channel in self.server.channels:
            if channel.has_user(self.identifier):
                channel.update_nicklist()
        w.nicklist_nick_set(self.server.buffer, self.nicklist_pointer, "visible", "0")
        buffer_list_update_next()

    def update_color(self):
        if colorize_nicks:
            if self.name == self.server.nick:
                self.color_name = w.config_string(w.config_get('weechat.color.chat_nick_self'))
            else:
                self.color_name = w.info_get('irc_nick_color_name', self.name)
            self.color = w.color(self.color_name)
        else:
            self.color = ""
            self.color_name = ""

    def formatted_name(self, prepend="", force_color=None):
        if colorize_nicks:
            print_color = force_color or self.color
        else:
            print_color = ""
        return print_color + prepend + self.name

    def open(self):
        t = time.time() + 1
        #reply = async_slack_api_request("im.open", {"channel":self.identifier,"ts":t})
        async_slack_api_request(self.server.domain, self.server.token, "im.open", {"user": self.identifier, "ts": t})

class Bot(object):

    def __init__(self, server, name, identifier, deleted=False):
        self.server = server
        self.name = name
        self.identifier = identifier
        self.deleted = deleted

    def __eq__(self, compare_str):
        if compare_str == self.identifier or compare_str == self.name:
            return True
        else:
            return False

    def __str__(self):
        return "{}".format(self.identifier)

    def __repr__(self):
        return "{}".format(self.identifier)

class Message(object):

    def __init__(self, message_json):
        self.message_json = message_json
        self.ts = message_json['ts']
        #split timestamp into time and counter
        self.ts_time, self.ts_counter = message_json['ts'].split('.')

    def change_text(self, new_text):
        if not isinstance(new_text, unicode):
            new_text = unicode(new_text, 'utf-8')
        self.message_json["text"] = new_text

    def add_reaction(self, reaction):
        if "reactions" in self.message_json:
            found = False
            for r in self.message_json["reactions"]:
                if r["name"] == reaction:
                    r["count"] += 1
                    found = True
            if not found:
                self.message_json["reactions"].append({u"count": 1, u"name": reaction})
        else:
            self.message_json["reactions"] = [{u"count": 1, u"name": reaction}]

    def remove_reaction(self, reaction):
        if "reactions" in self.message_json:
            for r in self.message_json["reactions"]:
                if r["name"] == reaction:
                    r["count"] -= 1
        else:
            pass

    def __eq__(self, other):
        return self.ts_time == other or self.ts == other

    def __repr__(self):
        return "{} {} {} {}\n".format(self.ts_time, self.ts_counter, self.ts, self.message_json)

    def __lt__(self, other):
        return self.ts < other.ts


def slack_command_cb(data, current_buffer, args):
    a = args.split(' ', 1)
    if len(a) > 1:
        function_name, args = a[0], " ".join(a[1:])
    else:
        function_name, args = a[0], None

    try:
        command = cmds[function_name](current_buffer, args)
    except KeyError:
        w.prnt("", "Command not found: " + function_name)
    return w.WEECHAT_RC_OK


def me_command_cb(data, current_buffer, args):
    if channels.find(current_buffer):
        channel = channels.find(current_buffer)
        nick = channel.server.nick
        message = "_{}_".format(args)
        buffer_input_cb("", current_buffer, message)
    return w.WEECHAT_RC_OK


def join_command_cb(data, current_buffer, args):
    if channels.find(current_buffer) or servers.find(current_buffer):
        channel = args.split()[1]
        channel = servers.find(current_domain_name()).channels.find(channel)
        channel.open()
        if w.config_get_plugin('switch_buffer_on_join') != '0':
            w.buffer_set(channel.channel_buffer, "display", "1")
        return w.WEECHAT_RC_OK_EAT
    else:
        return w.WEECHAT_RC_OK


def part_command_cb(data, current_buffer, args):
    if channels.find(current_buffer) or servers.find(current_buffer):
        args = args.split()
        if len(args) > 1:
            channel = args[1:]
            servers.find(current_domain_name()).channels.find(channel).close(True)
        else:
            channels.find(current_buffer).close(True)
        return w.WEECHAT_RC_OK_EAT
    else:
        return w.WEECHAT_RC_OK


# Wrap command_ functions that require they be performed in a slack buffer
def slack_buffer_required(f):
    @wraps(f)
    def wrapper(current_buffer, *args, **kwargs):
        server = servers.find(current_domain_name())
        if not server:
            w.prnt(current_buffer, "This command must be used in a slack buffer")
            return
        return f(current_buffer, *args, **kwargs)
    return wrapper


@slack_buffer_required
def command_talk(current_buffer, args):
    """
    Open a chat with the specified user
    /slack talk [user]
    """
    servers.find(current_domain_name()).users.find(args).open()


def command_join(current_buffer, args):
    """
    Join the specified channel
    /slack join [channel]
    """
    domain = current_domain_name()
    if domain == "":
        if len(servers) == 1:
            domain = servers[0]
        else:
            w.prnt(current_buffer, "You are connected to multiple Slack instances, please execute /join from a server buffer. i.e. (domain).slack.com")
            return
    channel = servers.find(domain).channels.find(args)
    if channel != None:
        servers.find(domain).channels.find(args).open()
    else:
        w.prnt(current_buffer, "Channel not found.")


@slack_buffer_required
def command_channels(current_buffer, args):
    """
    List all the channels for the slack instance (name, id, active)
    /slack channels
    """
    server = servers.find(current_domain_name())
    for channel in server.channels:
        line = "{:<25} {} {}".format(channel.name, channel.identifier, channel.active)
        server.buffer_prnt(line)


def command_nodistractions(current_buffer, args):
    global hide_distractions
    hide_distractions = not hide_distractions
    if distracting_channels != ['']:
        for channel in distracting_channels:
            try:
                channel_buffer = channels.find(channel).channel_buffer
                if channel_buffer:
                    w.buffer_set(channels.find(channel).channel_buffer, "hidden", str(int(hide_distractions)))
            except:
                dbg("Can't hide channel {}".format(channel), main_buffer=True)


def command_distracting(current_buffer, args):
    global distracting_channels
    distracting_channels = [x.strip() for x in w.config_get_plugin("distracting_channels").split(',')]
    if channels.find(current_buffer) is None:
        w.prnt(current_buffer, "This command must be used in a channel buffer")
        return
    fullname = channels.find(current_buffer).fullname()
    if distracting_channels.count(fullname) == 0:
        distracting_channels.append(fullname)
    else:
        distracting_channels.pop(distracting_channels.index(fullname))
    new = ','.join(distracting_channels)
    w.config_set_plugin('distracting_channels', new)


@slack_buffer_required
def command_users(current_buffer, args):
    """
    List all the users for the slack instance (name, id, away)
    /slack users
    """
    server = servers.find(current_domain_name())
    for user in server.users:
        line = "{:<40} {} {}".format(user.formatted_name(), user.identifier, user.presence)
        server.buffer_prnt(line)


def command_setallreadmarkers(current_buffer, args):
    """
    Sets the read marker for all channels
    /slack setallreadmarkers
    """
    for channel in channels:
        channel.mark_read()

def command_changetoken(current_buffer, args):
    w.config_set_plugin('slack_api_token', args)


def command_test(current_buffer, args):
    w.prnt(current_buffer, "worked!")


@slack_buffer_required
def command_away(current_buffer, args):
    """
    Sets your status as 'away'
    /slack away
    """
    server = servers.find(current_domain_name())
    async_slack_api_request(server.domain, server.token, 'presence.set', {"presence": "away"})


@slack_buffer_required
def command_back(current_buffer, args):
    """
    Sets your status as 'back'
    /slack back
    """
    server = servers.find(current_domain_name())
    async_slack_api_request(server.domain, server.token, 'presence.set', {"presence": "active"})


@slack_buffer_required
def command_markread(current_buffer, args):
    """
    Marks current channel as read
    /slack markread
    """
    # refactor this - one liner i think
    channel = current_buffer_name(short=True)
    domain = current_domain_name()
    if servers.find(domain).channels.find(channel):
        servers.find(domain).channels.find(channel).mark_read()

def command_flushcache(current_buffer, args):
    global message_cache
    message_cache = []
    cache_write_cb("","")

def command_cachenow(current_buffer, args):
    cache_write_cb("","")

def command_neveraway(current_buffer, args):
    global never_away
    if never_away:
        never_away = False
        dbg("unset never_away", main_buffer=True)
    else:
        never_away = True
        dbg("set never_away", main_buffer=True)


def command_printvar(current_buffer, args):
    w.prnt("", "{}".format(eval(args)))


def command_p(current_buffer, args):
    w.prnt("", "{}".format(eval(args)))


def command_debug(current_buffer, args):
    create_slack_debug_buffer()


def command_debugstring(current_buffer, args):
    global debug_string
    if args == '':
        debug_string = None
    else:
        debug_string = args


def command_search(current_buffer, args):
    pass
#    if not slack_buffer:
#        create_slack_buffer()
#    w.buffer_set(slack_buffer, "display", "1")
#    query = args
#    w.prnt(slack_buffer,"\nSearched for: %s\n\n" % (query))
#    reply = slack_api_request('search.messages', {"query":query}).read()
#    data = json.loads(reply)
#    for message in data['messages']['matches']:
#        message["text"] = message["text"].encode('ascii', 'ignore')
#        formatted_message = "%s / %s:\t%s" % (message["channel"]["name"], message['username'], message['text'])
#        w.prnt(slack_buffer,str(formatted_message))


def command_nick(current_buffer, args):
    pass
#    urllib.urlopen("https://%s/account/settings" % (domain))
#    browser.select_form(nr=0)
#    browser.form['username'] = args
#    reply = browser.submit()


def command_help(current_buffer, args):
    help_cmds = { k[8:]: v.__doc__ for k, v in globals().items() if k.startswith("command_") }

    if args:
        try:
             help_cmds = {args: help_cmds[args]}
        except KeyError:
            w.prnt("", "Command not found: " + args)
            return

    for cmd, helptext in help_cmds.items():
        w.prnt('', w.color("bold") + cmd)
        w.prnt('', (helptext or 'No help text').strip())
        w.prnt('', '')

# Websocket handling methods

def command_openweb(current_buffer, args):
    trigger = w.config_get_plugin('trigger_value')
    if trigger != "0":
        if args is None:
            channel = channels.find(current_buffer)
            url = "{}/messages/{}".format(channel.server.domain, channel.name)
            topic = w.buffer_get_string(channel.channel_buffer, "title")
            w.buffer_set(channel.channel_buffer, "title", "{}:{}".format(trigger, url))
            w.hook_timer(1000, 0, 1, "command_openweb", json.dumps({"topic": topic, "buffer": current_buffer}))
        else:
            #TODO: fix this dirty hack because i don't know the right way to send multiple args.
            args = current_buffer
            data = json.loads(args)
            channel_buffer = channels.find(data["buffer"]).channel_buffer
            w.buffer_set(channel_buffer, "title", data["topic"])
    return w.WEECHAT_RC_OK

def slack_websocket_cb(server, fd):
    try:
        data = servers.find(server).ws.recv()
        message_json = json.loads(data)
        # this magic attaches json that helps find the right dest
        message_json['myserver'] = server
    except:
        return w.WEECHAT_RC_OK
    # dispatch here
    if "reply_to" in message_json:
        function_name = "reply"
    elif "type" in message_json:
        function_name = message_json["type"]
    else:
        function_name = "unknown"
    try:
        proc[function_name](message_json)
        # dbg(function_name)
    except KeyError:
        if function_name:
            dbg("Function not implemented: {}\n{}".format(function_name, message_json))
        else:
            dbg("Function not implemented\n{}".format(message_json))
    w.bar_item_update("slack_typing_notice")
    return w.WEECHAT_RC_OK

def process_reply(message_json):
    global unfurl_ignore_alt_text

    server = servers.find(message_json["myserver"])
    identifier = message_json["reply_to"]
    item = server.message_buffer.pop(identifier)
    if "type" in item:
        if item["type"] == "message" and "channel" in item.keys():
            item["ts"] = message_json["ts"]
            channels.find(item["channel"]).cache_message(item, from_me=True)
            text = unfurl_refs(item["text"], ignore_alt_text=unfurl_ignore_alt_text)

            channels.find(item["channel"]).buffer_prnt(item["user"], text, item["ts"])
    dbg("REPLY {}".format(item))

def process_pong(message_json):
    pass


def process_pref_change(message_json):
    server = servers.find(message_json["myserver"])
    if message_json['name'] == u'muted_channels':
        muted = message_json['value'].split(',')
        for c in server.channels:
            if c.identifier in muted:
                c.muted = True
            else:
                c.muted = False
    else:
        dbg("Preference change not implemented: {}\n{}".format(message_json['name']))


def process_team_join(message_json):
    server = servers.find(message_json["myserver"])
    item = message_json["user"]
    server.add_user(User(server, item["name"], item["id"], item["presence"]))
    server.buffer_prnt(server.buffer, "New user joined: {}".format(item["name"]))

def process_manual_presence_change(message_json):
    process_presence_change(message_json)

def process_presence_change(message_json):
    server = servers.find(message_json["myserver"])
    identifier = message_json.get("user", server.nick)
    if message_json["presence"] == 'active':
        server.users.find(identifier).set_active()
    else:
        server.users.find(identifier).set_inactive()


def process_channel_marked(message_json):
    channel = channels.find(message_json["channel"])
    channel.mark_read(False)
    if not legacy_mode:
        w.buffer_set(channel.channel_buffer, "hotlist", "-1")


def process_group_marked(message_json):
    channel = channels.find(message_json["channel"])
    channel.mark_read(False)
    if not legacy_mode:
        w.buffer_set(channel.channel_buffer, "hotlist", "-1")


def process_channel_created(message_json):
    server = servers.find(message_json["myserver"])
    item = message_json["channel"]
    if server.channels.find(message_json["channel"]["name"]):
        server.channels.find(message_json["channel"]["name"]).open(False)
    else:
        item = message_json["channel"]
        server.add_channel(Channel(server, item["name"], item["id"], False))
    server.buffer_prnt("New channel created: {}".format(item["name"]))


def process_channel_left(message_json):
    server = servers.find(message_json["myserver"])
    server.channels.find(message_json["channel"]).close(False)


def process_channel_join(message_json):
    server = servers.find(message_json["myserver"])
    channel = server.channels.find(message_json["channel"])
    channel.user_join(message_json["user"])


def process_channel_topic(message_json):
    server = servers.find(message_json["myserver"])
    channel = server.channels.find(message_json["channel"])
    channel.set_topic(message_json["topic"])


def process_channel_joined(message_json):
    server = servers.find(message_json["myserver"])
    if server.channels.find(message_json["channel"]["name"]):
        server.channels.find(message_json["channel"]["name"]).open(False)
    else:
        item = message_json["channel"]
        server.add_channel(Channel(server, item["name"], item["id"], item["is_open"], item["last_read"], "#", item["members"], item["topic"]["value"]))


def process_channel_leave(message_json):
    server = servers.find(message_json["myserver"])
    channel = server.channels.find(message_json["channel"])
    channel.user_leave(message_json["user"])


def process_channel_archive(message_json):
    server = servers.find(message_json["myserver"])
    channel = server.channels.find(message_json["channel"])
    channel.detach_buffer()


def process_group_left(message_json):
    server = servers.find(message_json["myserver"])
    server.channels.find(message_json["channel"]).close(False)


def process_group_joined(message_json):
    server = servers.find(message_json["myserver"])
    if server.channels.find(message_json["channel"]["name"]):
        server.channels.find(message_json["channel"]["name"]).open(False)
    else:
        item = message_json["channel"]
        server.add_channel(GroupChannel(server, item["name"], item["id"], item["is_open"], item["last_read"], "#", item["members"], item["topic"]["value"]))


def  process_group_archive(message_json):
    channel = server.channels.find(message_json["channel"])
    channel.detach_buffer()


def process_im_close(message_json):
    server = servers.find(message_json["myserver"])
    server.channels.find(message_json["channel"]).close(False)


def process_im_open(message_json):
    server = servers.find(message_json["myserver"])
    server.channels.find(message_json["channel"]).open(False)


def process_im_marked(message_json):
    channel = channels.find(message_json["channel"])
    channel.mark_read(False)
    if not legacy_mode:
        w.buffer_set(channel.channel_buffer, "hotlist", "-1")


def process_im_created(message_json):
    server = servers.find(message_json["myserver"])
    item = message_json["channel"]
    channel_name = server.users.find(item["user"]).name
    if server.channels.find(channel_name):
        server.channels.find(channel_name).open(False)
    else:
        item = message_json["channel"]
        server.add_channel(DmChannel(server, channel_name, item["id"], item["is_open"], item["last_read"]))
    server.buffer_prnt("New channel created: {}".format(item["name"]))


def process_user_typing(message_json):
    server = servers.find(message_json["myserver"])
    channel = server.channels.find(message_json["channel"])
    if channel:
        channel.set_typing(server.users.find(message_json["user"]).name)


# todo: does this work?

def process_error(message_json):
    pass
    #connected = False

def process_reaction_added(message_json):
    channel = channels.find(message_json["item"]["channel"])
    channel.add_reaction(message_json["item"]["ts"], message_json["reaction"])

def process_reaction_removed(message_json):
    channel = channels.find(message_json["item"]["channel"])
    channel.remove_reaction(message_json["item"]["ts"], message_json["reaction"])

def create_reaction_string(reactions):
    if not isinstance(reactions, list):
        reaction_string = " [{}]".format(reactions)
    else:
        reaction_string = ' ['
        count = 0
        for r in reactions:
            if r["count"] > 0:
                count += 1
                reaction_string += ":{}:{} ".format(r["name"], r["count"])
        reaction_string = reaction_string[:-1] + ']'
    if count == 0:
        reaction_string = ''
    return reaction_string

# deprecated in favor of redrawing the entire buffer
#def modify_buffer_line(buffer, user, new_message, time, append):
#    time = int(float(time))
#    own_lines = w.hdata_pointer(w.hdata_get('buffer'), buffer, 'own_lines')
#    if own_lines:
#        line = w.hdata_pointer(w.hdata_get('lines'), own_lines, 'last_line')
#        hdata_line = w.hdata_get('line')
#        hdata_line_data = w.hdata_get('line_data')
#
#        while line:
#            data = w.hdata_pointer(hdata_line, line, 'data')
#            if data:
#                date = w.hdata_time(hdata_line_data, data, 'date')
#                prefix = w.hdata_string(hdata_line_data, data, 'prefix')
#                if new_message == "":
#                    new_message = w.hdata_string(hdata_line_data, data, 'message')
#                if user and (int(date) == int(time) and user == prefix):
#                    w.prnt("", "found matching time date is {}, time is {} ".format(date, time))
#                    w.hdata_update(hdata_line_data, data, {"message": "{}{}".format(new_message, append)})
#                    break
#                elif not user and (int(date) == int(time)):
#                    w.hdata_update(hdata_line_data, data, {"message": "{}{}".format(new_message, append)})
#                else:
#                    pass
#            line = w.hdata_move(hdata_line, line, -1)
#    return w.WEECHAT_RC_OK


def process_message(message_json, cache=True):
    global unfurl_ignore_alt_text

    try:
        # send these messages elsewhere
        known_subtypes = ['channel_join', 'channel_leave', 'channel_topic']
        if "subtype" in message_json and message_json["subtype"] in known_subtypes:
            proc[message_json["subtype"]](message_json)

        # move message properties down to root of json object
        message_json = unwrap_message(message_json)

        server = servers.find(message_json["myserver"])
        channel = channels.find(message_json["channel"])

        #do not process messages in unexpected channels
        if not channel.active:
            channel.open(False)
            dbg("message came for closed channel {}".format(channel.name))
            return

        time = message_json['ts']
        if "fallback" in message_json:
            text = message_json["fallback"]
        elif "text" in message_json:
            if message_json['text'] is not None:
                text = message_json["text"]
            else:
                text = ""
        else:
            text = ""

        #text = text.decode('utf-8')

        text = unfurl_refs(text, ignore_alt_text=unfurl_ignore_alt_text)

        if "attachments" in message_json:
            text += u" --- {}".format(unwrap_attachments(message_json))
        text = text.lstrip()
        text = text.replace("\t", "    ")
        name = get_user(message_json, server)

        text = text.encode('utf-8')
        name = name.encode('utf-8')

        if "reactions" in message_json:
            text += create_reaction_string(message_json["reactions"])

        if "subtype" in message_json and message_json["subtype"] == "message_changed":
                if "edited" in message_json["message"]:
                    append = " (edited)"
                else:
                    append = ''
                channel.change_message(message_json["message"]["ts"], text + append)
                cache=False
        elif "subtype" in message_json and message_json["subtype"] == "message_deleted":
            append = "(deleted)"
            text = ""
            channel.change_message(message_json["deleted_ts"], text + append)
            cache = False
        elif message_json.get("subtype", "") == "channel_leave":
            channel.buffer_prnt(w.prefix("quit").rstrip(), text, time)
        elif message_json.get("subtype", "") == "channel_join":
            channel.buffer_prnt(w.prefix("join").rstrip(), text, time)
        elif message_json.get("subtype", "") == "channel_topic":
            channel.buffer_prnt(w.prefix("network").rstrip(), text, time)
        else:
            channel.buffer_prnt(name, text, time)

        if cache:
            channel.cache_message(message_json)

    except Exception:
        if channel and ("text" in message_json) and message_json['text'] is not None:
            channel.buffer_prnt('unknown', message_json['text'])
        dbg("cannot process message {}\n{}".format(message_json, traceback.format_exc()))

def unwrap_message(message_json):
    if "message" in message_json:
        if "attachments" in message_json["message"]:
            message_json["attachments"] = message_json["message"]["attachments"]
        if "text" in message_json["message"]:
            if "text" in message_json:
                message_json["text"] += message_json["message"]["text"]
                dbg("added text!")
            else:
                message_json["text"] = message_json["message"]["text"]
        if "fallback" in message_json["message"]:
            if "fallback" in message_json:
                message_json["fallback"] += message_json["message"]["fallback"]
            else:
                message_json["fallback"] = message_json["message"]["fallback"]
    return message_json


def unwrap_attachments(message_json):
    attachment_text = ''
    for attachment in message_json["attachments"]:
        if "fallback" in attachment:
            attachment_text += attachment["fallback"]
#    attachment_text = attachment_text.encode('ascii', 'ignore')
    return attachment_text

def resolve_ref(ref):
    if ref.startswith('@U'):
        if users.find(ref[1:]):
            try:
                return "@{}".format(users.find(ref[1:]).name)
            except:
                dbg("NAME: {}".format(ref))
    elif ref.startswith('#C'):
        if channels.find(ref[1:]):
            try:
                return "{}".format(channels.find(ref[1:]).name)
            except:
                dbg("CHANNEL: {}".format(ref))

    # Something else, just return as-is
    return ref

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
                display_text = "{} ({})".format(url, desc)
    else:
        display_text = resolve_ref(ref)
    return display_text

def unfurl_refs(text, ignore_alt_text=False):
    """
    Worst code ever written. this needs work
    """
    if text and text.find('<') > -1:
        end = 0
        newtext = ""
        while text.find('<') > -1:
            # Prepend prefix
            newtext += text[:text.find('<')]
            text = text[text.find('<'):]
            end = text.find('>')
            if end == -1:
                newtext += text
                break
            # Format thingabob
            newtext += unfurl_ref(text[1:end], ignore_alt_text)
            text = text[end+1:]
        newtext += text
        return newtext
    return text


def get_user(message_json, server):
    if 'user' in message_json:
        name = server.users.find(message_json['user']).name
    elif 'username' in message_json:
        name = u"-{}-".format(message_json["username"])
    elif 'bot_id' in message_json:
        name = u"{}:]".format(server.bots.find(message_json["bot_id"]).name)
    elif 'service_name' in message_json:
        name = u"-{}-".format(message_json["service_name"])
    else:
        name = u""
    return name

# END Websocket handling methods


def typing_bar_item_cb(data, buffer, args):
    typers = [x for x in channels if x.is_someone_typing()]
    if len(typers) > 0:
        direct_typers = []
        channel_typers = []
        for dm in channels.find_by_class(DmChannel):
            direct_typers.extend(dm.get_typing_list())
        direct_typers = ["D/" + x for x in direct_typers]
        current_channel = w.current_buffer()
        channel = channels.find(current_channel)
        try:
            if channel and channel.__class__ != DmChannel:
                channel_typers = channels.find(current_channel).get_typing_list()
        except:
            w.prnt("", "Bug on {}".format(channel))
        typing_here = ", ".join(channel_typers + direct_typers)
        if len(typing_here) > 0:
            color = w.color('yellow')
            return color + "typing: " + typing_here
    return ""


def typing_update_cb(data, remaining_calls):
    w.bar_item_update("slack_typing_notice")
    return w.WEECHAT_RC_OK


def buffer_list_update_cb(data, remaining_calls):
    global buffer_list_update

    now = time.time()
    if buffer_list_update and previous_buffer_list_update + 1 < now:
        gray_check = False
        if len(servers) > 1:
            gray_check = True
        for channel in channels:
            channel.rename()
        buffer_list_update = False
    return w.WEECHAT_RC_OK

def buffer_list_update_next():
    global buffer_list_update
    buffer_list_update = True

def hotlist_cache_update_cb(data, remaining_calls):
    # this keeps the hotlist dupe up to date for the buffer switch, but is prob technically a race condition. (meh)
    global hotlist
    prev_hotlist = hotlist
    hotlist = w.infolist_get("hotlist", "", "")
    w.infolist_free(prev_hotlist)
    return w.WEECHAT_RC_OK


def buffer_closing_cb(signal, sig_type, data):
    if channels.find(data):
        channels.find(data).closed()
    return w.WEECHAT_RC_OK


def buffer_switch_cb(signal, sig_type, data):
    global previous_buffer, hotlist
    # this is to see if we need to gray out things in the buffer list
    buffer_list_update_next()
    if channels.find(previous_buffer):
        channels.find(previous_buffer).mark_read()

    channel_name = current_buffer_name()
    previous_buffer = data
    return w.WEECHAT_RC_OK


def typing_notification_cb(signal, sig_type, data):
    if len(w.buffer_get_string(data, "input")) > 8:
        global typing_timer
        now = time.time()
        if typing_timer + 4 < now:
            channel = channels.find(current_buffer_name())
            if channel:
                identifier = channel.identifier
                request = {"type": "typing", "channel": identifier}
                channel.server.send_to_websocket(request, expect_reply=False)
                typing_timer = now
    return w.WEECHAT_RC_OK

def slack_ping_cb(data, remaining):
    """
    Periodic websocket ping to detect broken connection.
    """
    servers.find(data).ping()
    return w.WEECHAT_RC_OK


def slack_connection_persistence_cb(data, remaining_calls):
    """
    Reconnect if a connection is detected down
    """
    for server in servers:
        if not server.connected:
            server.buffer_prnt("Disconnected from slack, trying to reconnect..")
            if server.ws_hook is not None:
                w.unhook(server.ws_hook)
            server.connect_to_slack()
    return w.WEECHAT_RC_OK


def slack_never_away_cb(data, remaining):
    global never_away
    if never_away:
        for server in servers:
            identifier = server.channels.find("slackbot").identifier
            request = {"type": "typing", "channel": identifier}
            #request = {"type":"typing","channel":"slackbot"}
            server.send_to_websocket(request, expect_reply=False)
    return w.WEECHAT_RC_OK


def nick_completion_cb(data, completion_item, buffer, completion):
    """
    Adds all @-prefixed nicks to completion list
    """

    channel = channels.find(buffer)
    if channel is None or channel.members is None:
        return w.WEECHAT_RC_OK
    for m in channel.members:
        user = channel.server.users.find(m)
        w.hook_completion_list_add(completion, "@" + user.name, 1, w.WEECHAT_LIST_POS_SORT)
    return w.WEECHAT_RC_OK


def complete_next_cb(data, buffer, command):
    """Extract current word, if it is equal to a nick, prefix it with @ and
    rely on nick_completion_cb adding the @-prefixed versions to the
    completion lists, then let Weechat's internal completion do its
    thing

    """

    channel = channels.find(buffer)
    if channel is None or channel.members is None:
        return w.WEECHAT_RC_OK
    input = w.buffer_get_string(buffer, "input")
    current_pos = w.buffer_get_integer(buffer, "input_pos") - 1
    input_length = w.buffer_get_integer(buffer, "input_length")
    word_start = 0
    word_end = input_length
    # If we're on a non-word, look left for something to complete
    while current_pos >= 0 and input[current_pos] != '@' and not input[current_pos].isalnum():
        current_pos = current_pos - 1
    if current_pos < 0:
        current_pos = 0
    for l in range(current_pos, 0, -1):
        if input[l] != '@' and not input[l].isalnum():
            word_start = l + 1
            break
    for l in range(current_pos, input_length):
        if not input[l].isalnum():
            word_end = l
            break
    word = input[word_start:word_end]
    for m in channel.members:
        user = channel.server.users.find(m)
        if user.name == word:
            # Here, we cheat.  Insert a @ in front and rely in the @
            # nicks being in the completion list
            w.buffer_set(buffer, "input", input[:word_start] + "@" + input[word_start:])
            w.buffer_set(buffer, "input_pos", str(w.buffer_get_integer(buffer, "input_pos") + 1))
            return w.WEECHAT_RC_OK_EAT
    return w.WEECHAT_RC_OK

# Slack specific requests

# NOTE: switched to async because sync slowed down the UI
def async_slack_api_request(domain, token, request, post_data, priority=False):
    if not STOP_TALKING_TO_SLACK:
        post_data["token"] = token
        url = 'url:https://{}/api/{}?{}'.format(domain, request, urllib.urlencode(post_data))
        context = pickle.dumps({"request": request, "token": token, "post_data": post_data})
        params = { 'useragent': 'wee_slack {}'.format(SCRIPT_VERSION) }
        dbg("URL: {} context: {} params: {}".format(url, context, params))
        w.hook_process_hashtable(url, params, 20000, "url_processor_cb", context)

# funny, right?
big_data = {}

def url_processor_cb(data, command, return_code, out, err):
    global big_data
    data = pickle.loads(data)
    identifier = sha.sha("{}{}".format(data, command)).hexdigest()
    if identifier not in big_data:
        big_data[identifier] = ''
    big_data[identifier] += out
    if return_code == 0:
        try:
            my_json = json.loads(big_data[identifier])
        except:
            dbg("request failed, doing again...")
            dbg("response length: {} identifier {}\n{}".format(len(big_data[identifier]), identifier, data))
            my_json = False

        big_data.pop(identifier, None)

        if my_json:
            if data["request"] == 'rtm.start':
                servers.find(data["token"]).connected_to_slack(my_json)
                servers.update_hashtable()

            else:
                if "channel" in data["post_data"]:
                    channel = data["post_data"]["channel"]
                token = data["token"]
                if "messages" in my_json:
                    messages = my_json["messages"].reverse()
                    for message in my_json["messages"]:
                        message["myserver"] = servers.find(token).domain
                        message["channel"] = servers.find(token).channels.find(channel).identifier
                        process_message(message)
                if "channel" in my_json:
                    if "members" in my_json["channel"]:
                        channels.find(my_json["channel"]["id"]).members = set(my_json["channel"]["members"])
    else:
        if return_code != -1:
            big_data.pop(identifier, None)
        dbg("return code: {}, data: {}".format(return_code, data))

    return w.WEECHAT_RC_OK

def cache_write_cb(data, remaining):
    cache_file = open("{}/{}".format(WEECHAT_HOME, CACHE_NAME), 'w')
    for channel in channels:
        if channel.active:
            for message in channel.messages:
                cache_file.write("{}\n".format(json.dumps(message.message_json)))
    return w.WEECHAT_RC_OK

def cache_load():
    global message_cache
    try:
        file_name = "{}/{}".format(WEECHAT_HOME, CACHE_NAME)
        if sum(1 for line in open('myfile.txt')) > 2:
            cache_file = open(file_name, 'r')
            for line in cache_file:
                message_cache.append(line)
    except IOError:
        #cache file didn't exist
        pass

def cache_get(channel):
    lines = []
    for line in message_cache:
        j = json.loads(line)
        if j["channel"] == channel:
            lines.append(line)
    return lines

# END Slack specific requests

# Utility Methods


def current_domain_name():
    buffer = w.current_buffer()
    if servers.find(buffer):
        return servers.find(buffer).domain
    else:
        #number = w.buffer_get_integer(buffer, "number")
        name = w.buffer_get_string(buffer, "name")
        name = ".".join(name.split(".")[:-1])
        return name


def current_buffer_name(short=False):
    buffer = w.current_buffer()
    #number = w.buffer_get_integer(buffer, "number")
    name = w.buffer_get_string(buffer, "name")
    if short:
        try:
            name = name.split('.')[-1]
        except:
            pass
    return name


def closed_slack_buffer_cb(data, buffer):
    global slack_buffer
    slack_buffer = None
    return w.WEECHAT_RC_OK


def create_slack_buffer():
    global slack_buffer
    slack_buffer = w.buffer_new("slack", "", "", "closed_slack_buffer_cb", "")
    w.buffer_set(slack_buffer, "notify", "0")
    #w.buffer_set(slack_buffer, "display", "1")
    return w.WEECHAT_RC_OK


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


def config_changed_cb(data, option, value):
    global slack_api_token, distracting_channels, channels_not_on_current_server_color, colorize_nicks, slack_debug, debug_mode, \
        unfurl_ignore_alt_text

    slack_api_token = w.config_get_plugin("slack_api_token")

    if slack_api_token.startswith('${sec.data'):
        slack_api_token = w.string_eval_expression(slack_api_token, {}, {}, {})

    distracting_channels = [x.strip() for x in w.config_get_plugin("distracting_channels").split(',')]
    channels_not_on_current_server_color = w.config_get_plugin("channels_not_on_current_server_color")
    if channels_not_on_current_server_color == "0":
        channels_not_on_current_server_color = False
    colorize_nicks = w.config_get_plugin('colorize_nicks') == "1"
    debug_mode = w.config_get_plugin("debug_mode").lower()
    if debug_mode != '' and debug_mode != 'false':
        create_slack_debug_buffer()

    unfurl_ignore_alt_text = False
    if w.config_get_plugin('unfurl_ignore_alt_text') != "0":
        unfurl_ignore_alt_text = True

    return w.WEECHAT_RC_OK

def quit_notification_cb(signal, sig_type, data):
    stop_talking_to_slack()

def script_unloaded():
    stop_talking_to_slack()
    return w.WEECHAT_RC_OK

def stop_talking_to_slack():
    """
    Prevents a race condition where quitting closes buffers
    which triggers leaving the channel because of how close
    buffer is handled
    """
    global STOP_TALKING_TO_SLACK
    STOP_TALKING_TO_SLACK = True
    cache_write_cb("", "")
    return w.WEECHAT_RC_OK

def scrolled_cb(signal, sig_type, data):
    try:
        if w.window_get_integer(data, "scrolling") == 1:
            channels.find(w.current_buffer()).set_scrolling()
        else:
            channels.find(w.current_buffer()).unset_scrolling()
    except:
        pass
    return w.WEECHAT_RC_OK

# END Utility Methods

# Main
if __name__ == "__main__":
    if w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE,
                  SCRIPT_DESC, "script_unloaded", ""):

        WEECHAT_HOME = w.info_get("weechat_dir", "")
        CACHE_NAME = "slack.cache"
        STOP_TALKING_TO_SLACK = False

        if not w.config_get_plugin('slack_api_token'):
            w.config_set_plugin('slack_api_token', "INSERT VALID KEY HERE!")
        if not w.config_get_plugin('distracting_channels'):
            w.config_set_plugin('distracting_channels', "")
        if not w.config_get_plugin('channels_not_on_current_server_color'):
            w.config_set_plugin('channels_not_on_current_server_color', "0")
        if not w.config_get_plugin('debug_mode'):
            w.config_set_plugin('debug_mode', "")
        if not w.config_get_plugin('colorize_nicks'):
            w.config_set_plugin('colorize_nicks', "1")
        if not w.config_get_plugin('trigger_value'):
            w.config_set_plugin('trigger_value', "0")
        if not w.config_get_plugin('unfurl_ignore_alt_text'):
            w.config_set_plugin('unfurl_ignore_alt_text', "0")
        if not w.config_get_plugin('switch_buffer_on_join'):
            w.config_set_plugin('switch_buffer_on_join', "1")

        version = w.info_get("version_number", "") or 0
        if int(version) >= 0x00040400:
            legacy_mode = False
        else:
            legacy_mode = True

        # Global var section
        slack_debug = None
        config_changed_cb("", "", "")

        cmds = {k[8:]: v for k, v in globals().items() if k.startswith("command_")}
        proc = {k[8:]: v for k, v in globals().items() if k.startswith("process_")}

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

        message_cache = []
        cache_load()

        servers = SearchList()
        for token in slack_api_token.split(','):
            server = SlackServer(token)
            servers.append(server)
        channels = SearchList()
        users = SearchList()

        w.hook_config("plugins.var.python." + SCRIPT_NAME + ".*", "config_changed_cb", "")
        w.hook_timer(3000, 0, 0, "slack_connection_persistence_cb", "")

        # attach to the weechat hooks we need
        w.hook_timer(1000, 0, 0, "typing_update_cb", "")
        w.hook_timer(1000, 0, 0, "buffer_list_update_cb", "")
        w.hook_timer(1000, 0, 0, "hotlist_cache_update_cb", "")
        w.hook_timer(1000 * 60 * 29, 0, 0, "slack_never_away_cb", "")
        w.hook_timer(1000 * 60 * 5, 0, 0, "cache_write_cb", "")
        w.hook_signal('buffer_closing', "buffer_closing_cb", "")
        w.hook_signal('buffer_switch', "buffer_switch_cb", "")
        w.hook_signal('window_switch', "buffer_switch_cb", "")
        w.hook_signal('input_text_changed', "typing_notification_cb", "")
        w.hook_signal('quit', "quit_notification_cb", "")
        w.hook_signal('window_scrolled', "scrolled_cb", "")
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
#        w.hook_command('me', 'me_command_cb', '')
        w.hook_command('me', '', 'stuff', 'stuff2', '', 'me_command_cb', '')
        w.hook_command_run('/query', 'join_command_cb', '')
        w.hook_command_run('/join', 'join_command_cb', '')
        w.hook_command_run('/part', 'part_command_cb', '')
        w.hook_command_run('/leave', 'part_command_cb', '')
        w.hook_command_run("/input complete_next", "complete_next_cb", "")
        w.hook_completion("nicks", "complete @-nicks for slack",
                          "nick_completion_cb", "")
        w.bar_item_new('slack_typing_notice', 'typing_bar_item_cb', '')
        # END attach to the weechat hooks we need

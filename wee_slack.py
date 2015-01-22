# -*- coding: utf-8 -*-
#
import time
import json
import pickle
import sha
import re
import urllib
import urlparse
import HTMLParser
from websocket import create_connection

# hack to make tests possible.. better way?
try:
    import weechat as w
except:
    pass

SCRIPT_NAME = "slack_extension"
SCRIPT_AUTHOR = "Ryan Huber <rhuber@gmail.com>"
SCRIPT_VERSION = "0.97.15"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Extends weechat for typing notification/search/etc on slack.com"

BACKLOG_SIZE = 200

SLACK_API_TRANSLATOR = {
    "channel": {
        "history": "channels.history",
        "join": "channels.join",
        "leave": "channels.leave",
        "mark": "channels.mark",
        "info": "channels.info"
    },
    "im": {
        "history": "im.history",
        "leave": "im.close",
        "mark": "im.mark"
    },
    "group": {
        "history": "groups.history",
        "join": "channels.join",
        "leave": "groups.leave",
        "mark": "groups.mark"
    }

}

def dbg(message, fout=False, main_buffer=False):
    message = "DEBUG: {}".format(message)
    #message = message.encode('utf-8', 'replace')
    if fout:
        file('/tmp/debug.log', 'a+').writelines(message + '\n')
    if slack_debug is not None:
        if not main_buffer:
            w.prnt(slack_debug, message)
        else:
            w.prnt("", message)

# hilarious, i know


class Meta(list):

    def __init__(self, attribute, search_list):
        self.attribute = attribute
        self.search_list = search_list

    def __str__(self):
        string = ''
        for each in self.search_list.get_all(self.attribute):
            string += "{} ".format(each)
        return string

    def __repr__(self):
        self.search_list.get_all(self.attribute)

    def __getitem__(self, index):
        things = self.get_all()
        return things[index]

    def __iter__(self):
        things = self.get_all()
        for channel in things:
            yield channel

    def get_all(self):
        items = []
        items += self.search_list.get_all(self.attribute)
        return items

    def find(self, name):
        items = self.search_list.find_deep(name, self.attribute)
        items = [x for x in items if x is not None]
        if len(items) == 1:
            return items[0]
        elif len(items) == 0:
            pass
        else:
            dbg("probably something bad happened with meta items: {}".format(items))
            return items
            #raise AmbiguousProblemError

    def find_first(self, name):
        items = self.find(name)
        if items.__class__ == list:
            return items[0]
        else:
            return False

    def find_by_class(self, class_name):
        items = self.search_list.find_by_class_deep(class_name, self.attribute)
        return items


class SearchList(list):

    def find(self, name):
        items = []
        for child in self:
            if child.__class__ == self.__class__:
                items += child.find(name)
            else:
                if child == name:
                    items.append(child)
        if len(items) == 1:
            return items[0]
        elif items != []:
            return items

    def find_deep(self, name, attribute):
        items = []
        for child in self:
            if child.__class__ == self.__class__:
                if items is not None:
                    items += child.find_deep(name, attribute)
            elif dir(child).count('find') == 1:
                if items is not None:
                    items.append(child.find(name, attribute))
        if items != []:
            return items

    def get_all(self, attribute):
        items = []
        for child in self:
            if child.__class__ == self.__class__:
                items += child.get_all(attribute)
            else:
                items += (eval("child." + attribute))
        return items

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
        self.channels = SearchList()
        self.connecting = False
        self.connected = False
        self.ping_counter = 0
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

    def find(self, name, attribute):
        attribute = eval("self." + attribute)
        return attribute.find(name)

    def send_to_websocket(self, data):
        try:
            self.ws.send(data)
            dbg("Sent {}...".format(data[:100]))
        except:
            self.connected = False

    def ping(self):
        if self.ping_counter > 999:
            self.ping_counter = 0
        request = {"type": "ping", "id": self.ping_counter}
        self.send_to_websocket(json.dumps(request))
        self.ping_counter += 1

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
                    self.ping_counter = 0
                self.ping_hook = w.hook_timer(1000 * 5, 0, 0, "slack_ping_cb", self.domain)
                if len(self.users) and 0 or len(self.channels) == 0:
                    self.create_slack_mappings(login_data)

                self.connected = True
                self.connecting = False

                self.print_connection_info(login_data)
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

    def create_slack_websocket(self, data):
        web_socket_url = data['url']
        try:
            self.ws = create_connection(web_socket_url)
            self.ws_hook = w.hook_fd(self.ws.sock._sock.fileno(), 1, 0, 0, "slack_websocket_cb", self.identifier)
            self.ws.sock.setblocking(0)
            return True
        except:
            return False

    def create_slack_mappings(self, data):

        for item in data["users"]:
            self.users.append(User(self, item["name"], item["id"], item["presence"]))

        for item in data["channels"]:
            if "last_read" not in item:
                item["last_read"] = 0
            if "members" not in item:
                item["members"] = []
            if "topic" not in item:
                item["topic"] = {}
                item["topic"]["value"] = ""
            self.channels.append(Channel(self, item["name"], item["id"], item["is_member"], item["last_read"], "#", item["members"], item["topic"]["value"]))
        for item in data["groups"]:
            if "last_read" not in item:
                item["last_read"] = 0
            self.channels.append(GroupChannel(self, item["name"], item["id"], item["is_open"], item["last_read"], "#", item["members"], item["topic"]["value"]))
        for item in data["ims"]:
            if "last_read" not in item:
                item["last_read"] = 0
            name = self.users.find(item["user"]).name
            self.channels.append(DmChannel(self, name, item["id"], item["is_open"], item["last_read"]))

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


class SlackThing(object):

    def __init__(self, name, identifier):
        self.name = name
        self.identifier = identifier
        self.channel_buffer = None

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name


def buffer_input_cb(b, buffer, data):
    channel = channels.find(buffer)
    channel.send_message(data)
    channel.buffer_prnt(channel.server.nick, data)
    channel.mark_read(True)
    return w.WEECHAT_RC_ERROR


class Channel(SlackThing):

    def __init__(self, server, name, identifier, active, last_read=0, prepend_name="", members=[], topic=""):
        super(Channel, self).__init__(name, identifier)
        self.type = "channel"
        self.server = server
        self.name = prepend_name + self.name
        self.typing = {}
        self.active = active
        self.opening = False
        self.members = set(members)
        self.topic = topic
        self.last_read = float(last_read)
        self.last_received = None
        self.previous_prnt_name = ""
        self.previous_prnt_message = ""
        if active:
            self.create_buffer()
            self.attach_buffer()
            self.update_nicklist()
            self.set_topic(self.topic)
            buffer_list_update_next()

    def __eq__(self, compare_str):
        if compare_str == self.fullname() or compare_str == self.name or compare_str == self.identifier or compare_str == self.name[1:] or (compare_str == self.channel_buffer and self.channel_buffer is not None):
            return True
        else:
            return False

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

    def attach_buffer(self):
        channel_buffer = w.buffer_search("", "{}.{}".format(self.server.domain, self.name))
        if channel_buffer != main_weechat_buffer:
            self.channel_buffer = channel_buffer
#            w.buffer_set(self.channel_buffer, "highlight_words", self.server.nick)
        else:
            self.channel_buffer = None

    def detach_buffer(self):
        if self.channel_buffer is not None:
            w.buffer_close(self.channel_buffer)
            self.channel_buffer = None

    def update_nicklist(self):
        w.buffer_set(self.channel_buffer, "nicklist", "1")
        w.nicklist_remove_all(self.channel_buffer)
        try:
            for user in self.members:
                user = self.server.users.find(user)
                if user.presence == 'away':
                    w.nicklist_add_nick(self.channel_buffer, "", user.name, user.color_name, " ", "", 1)
                else:
                    w.nicklist_add_nick(self.channel_buffer, "", user.name, user.color_name, "+", "", 1)
        except:
            print "DEBUG: {} {}".format(self.identifier,self.name)

    def fullname(self):
        return "{}.{}".format(self.server.domain, self.name)

    def has_user(self, name):
        return name in self.members

    def user_join(self, name):
        self.members.add(name)
        self.update_nicklist()

    def user_leave(self, name):
        if name in self.members:
            self.members.remove(name)
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
        request = {"type": "message", "channel": self.identifier, "text": message}
        self.server.send_to_websocket(json.dumps(request))

    def linkify_text(self, message):
        message = message.split(' ')
        for item in enumerate(message):
            if item[1].startswith('@'):
                named = re.match('.*[@#](\w+)(\W*)', item[1]).groups()
                if self.server.users.find(named[0]):
                    message[item[0]] = "<@{}>{}".format(self.server.users.find(named[0]).identifier, named[1])
            if item[1].startswith('#') and self.server.channels.find(item[1]):
                named = re.match('.*[@#](\w+)(\W*)', item[1]).groups()
                if self.server.channels.find(named[0]):
                    message[item[0]] = "<#{}>{}".format(self.server.channels.find(named[0]).identifier, named[1])
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
        async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["info"], {"name": self.name.lstrip("#")})
        if update_remote:
            async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["join"], {"name": self.name.lstrip("#")})
        self.opening = False

    def close(self, update_remote=True):
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
            color = channels_not_on_current_server_color
        else:
            color = "default"
        color = w.color(color)
        if self.is_someone_typing():
            new_name = ">{}".format(self.name[1:])
        else:
            new_name = self.name
        if self.channel_buffer:
            if w.buffer_get_string(self.channel_buffer, "short_name") != (color + new_name):
                w.buffer_set(self.channel_buffer, "short_name", color + new_name)

    def buffer_prnt(self, user='unknown user', message='no message', time=0):
        set_read_marker = False
        time_float = float(time)
        if time_float != 0 and self.last_read >= time_float:
            tags = "no_highlight,notify_none,logger_backlog_end"
            set_read_marker = True
        elif message.find(self.server.nick.encode('utf-8')) > -1:
            tags = "notify_highlight"
        elif user != self.server.nick and self.name in self.server.users:
            tags = "notify_private,notify_message"
        else:
            tags = "notify_message"
        time_int = int(time_float)
        if self.channel_buffer:
            if self.server.users.find(user) and user != self.server.nick:
                name = self.server.users.find(user).formatted_name()
            else:
                name = user
            name = name.decode('utf-8')
            message = message.decode('UTF-8', 'replace')
            if message != self.previous_prnt_message:
                if message.startswith(self.previous_prnt_message):
                    message = message[len(self.previous_prnt_message):]
                message = HTMLParser.HTMLParser().unescape(message)
                data = u"{}\t{}".format(name, message).encode('utf-8')
                w.prnt_date_tags(self.channel_buffer, time_int, tags, data)
            self.previous_prnt_message = message
            if set_read_marker:
                self.mark_read(False)
        else:
            self.open(False)
        self.last_received = time
        self.unset_typing(user)

    def get_history(self):
        if self.active:
            if self.identifier in message_cache.keys():
                for message in message_cache[self.identifier]:
                    process_message(message)
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


class User(SlackThing):

    def __init__(self, server, name, identifier, presence="away"):
        super(User, self).__init__(name, identifier)
        self.channel_buffer = w.info_get("irc_buffer", "{}.{}".format(domain, self.name))
        self.presence = presence
        self.server = server
        self.update_color()
        if self.presence == 'away':
            self.nicklist_pointer = w.nicklist_add_nick(server.buffer, "", self.name, self.color_name, " ", "", 0)
        else:
            self.nicklist_pointer = w.nicklist_add_nick(server.buffer, "", self.name, self.color_name, "+", "", 1)
#        w.nicklist_add_nick(server.buffer, "", self.formatted_name(), "", "", "", 1)

    def __eq__(self, compare_str):
        if compare_str == self.name or compare_str == "@" + self.name or compare_str == self.identifier:
            return True
        else:
            return False

    def set_active(self):
        self.presence = "active"
        for channel in self.server.channels:
            if channel.has_user(self.identifier):
                channel.update_nicklist()
        w.nicklist_nick_set(self.server.buffer, self.nicklist_pointer, "prefix", "+")
        w.nicklist_nick_set(self.server.buffer, self.nicklist_pointer, "visible", "1")
        buffer_list_update_next()

    def set_inactive(self):
        self.presence = "away"
        for channel in self.server.channels:
            if channel.has_user(self.identifier):
                channel.update_nicklist()
        w.nicklist_nick_set(self.server.buffer, self.nicklist_pointer, "prefix", " ")
        w.nicklist_nick_set(self.server.buffer, self.nicklist_pointer, "visible", "0")
        buffer_list_update_next()

    def update_color(self):
        if colorize_nicks:
            self.color = w.info_get('irc_nick_color', self.name)
            self.color_name = w.info_get('irc_nick_color_name', self.name)
        else:
            self.color = ""
            self.color_name = ""

    def formatted_name(self, prepend="", force_color=None):
        if colorize_nicks:
            if not force_color:
                print_color = self.color
            else:
                print_color = force_color
            return print_color + prepend + self.name
        else:
            return prepend + self.name

    def open(self):
        t = time.time() + 1
        #reply = async_slack_api_request("im.open", {"channel":self.identifier,"ts":t})
        async_slack_api_request(self.server.domain, self.server.token, "im.open", {"user": self.identifier, "ts": t})


def slack_command_cb(data, current_buffer, args):
    a = args.split(' ', 1)
    if len(a) > 1:
        function_name, args = a[0], " ".join(a[1:])
    else:
        function_name, args = a[0], None
#    try:
    cmds[function_name](current_buffer, args)
#    except KeyError:
#        w.prnt("", "Command not found or exception: "+function_name)
    return w.WEECHAT_RC_OK


def me_command_cb(data, current_buffer, args):
    if channels.find(current_buffer):
        channel = channels.find(current_buffer)
        nick = channel.server.nick
        message = "{} {}".format(nick, args)
        message = message.encode('utf-8')
        buffer_input_cb("", current_buffer, message)
    return w.WEECHAT_RC_OK


def join_command_cb(data, current_buffer, args):
    if channels.find(current_buffer) or servers.find(current_buffer):
        channel = args.split()[1]
        servers.find(current_domain_name()).channels.find(channel).open()
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


def command_talk(current_buffer, args):
    servers.find(current_domain_name()).users.find(args).open()


def command_join(current_buffer, args):
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

def command_channels(current_buffer, args):
    server = servers.find(current_domain_name())
    for channel in server.channels:
        line = "{:<25} {} {}".format(channel.name, channel.identifier, channel.active)
        server.buffer_prnt(line)


def command_users(current_buffer, args):
    server = servers.find(current_domain_name())
    for user in server.users:
        line = "{:<40} {} {}".format(user.formatted_name(), user.identifier, user.presence)
        server.buffer_prnt(line)


def command_setallreadmarkers(current_buffer, args):
    if args:
        for channel in channels:
            channel.set_read_marker(args)


def command_changetoken(current_buffer, args):
    w.config_set_plugin('slack_api_token', args)


def command_test(current_buffer, args):
    w.prnt(current_buffer, "worked!")


def command_away(current_buffer, args):
    server = servers.find(current_domain_name())
    async_slack_api_request(server.domain, server.token, 'presence.set', {"presence": "away"})


def command_back(current_buffer, args):
    server = servers.find(current_domain_name())
    async_slack_api_request(server.domain, server.token, 'presence.set', {"presence": "active"})


def command_markread(current_buffer, args):
    # refactor this - one liner i think
    channel = current_buffer_name(short=True)
    domain = current_domain_name()
    if servers.find(domain).channels.find(channel):
        servers.find(domain).channels.find(channel).mark_read()

def command_cacheinfo(current_buffer, args):
    for channel in message_cache.keys():
        c = channels.find(channel)
        w.prnt("", "{} {}".format(channels.find(channel), len(message_cache[channel])))
#        server.buffer_prnt("{} {}".format(channels.find(channel), len(message_cache[channel])))

def command_uncache(current_buffer, args):
    identifier = channels.find(current_buffer).identifier
    message_cache.pop(identifier)
    cache_write_cb("","")

def command_cachenow(current_buffer, args):
    cache_write_cb("","")

def command_neveraway(current_buffer, args):
    global never_away
    if never_away:
        never_away = False
        dbg("unset never_away")
    else:
        never_away = True
        dbg("set never_away")


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

# Websocket handling methods


def slack_websocket_cb(server, fd):
    try:
        data = servers.find(server).ws.recv()
        message_json = json.loads(data)
        # this magic attaches json that helps find the right dest
        message_json['myserver'] = server
    except:
        return w.WEECHAT_RC_OK
    # dispatch here
    if "type" in message_json:
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


def process_pong(message_json):
    pass


def process_team_join(message_json):
    server = servers.find(message_json["myserver"])
    item = message_json["user"]
    server.users.append(User(server, item["name"], item["id"], item["presence"]))
    server.buffer_prnt(server.buffer, "New user joined: {}".format(item["name"]))


def process_presence_change(message_json):
    buffer_name = "{}.{}".format(domain, message_json["user"])
    buf_ptr = w.buffer_search("", buffer_name)
    if message_json["presence"] == 'active':
        users.find(message_json["user"]).set_active()
    else:
        users.find(message_json["user"]).set_inactive()


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
        server.channels.append(Channel(server, item["name"], item["id"], item["is_open"], item["last_read"], "#", item["members"], item["topic"]))
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
        server.channels.append(Channel(server, item["name"], item["id"], item["is_open"], item["last_read"], "#", item["members"], item["topic"]))


def process_channel_leave(message_json):
    server = servers.find(message_json["myserver"])
    channel = server.channels.find(message_json["channel"])
    channel.user_leave(message_json["user"])


def process_group_left(message_json):
    server = servers.find(message_json["myserver"])
    server.channels.find(message_json["channel"]).close(False)


def process_group_joined(message_json):
    server = servers.find(message_json["myserver"])
    if server.channels.find(message_json["channel"]["name"]):
        server.channels.find(message_json["channel"]["name"]).open(False)
    else:
        item = message_json["channel"]
        server.channels.append(GroupChannel(server, item["name"], item["id"], item["is_open"], item["last_read"], "#", item["members"], item["topic"]))


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
        server.channels.append(DmChannel(server, channel_name, item["id"], item["is_open"], item["last_read"]))
    server.buffer_prnt("New channel created: {}".format(item["name"]))


def process_user_typing(message_json):
    server = servers.find(message_json["myserver"])
    server.channels.find(message_json["channel"]).set_typing(server.users.find(message_json["user"]).name)

# todo: does this work?


def process_error(message_json):
    pass
    #connected = False

# def process_message_changed(message_json):
#    process_message(message_json)

def cache_message(message_json):
    global message_cache

    channel = message_json["channel"]
    if channel not in message_cache:
        message_cache[channel] = []
    if message_json not in message_cache[channel]:
        message_cache[channel].append(message_json)
    if len(message_cache[channel]) > BACKLOG_SIZE:
        message_cache[channel] = message_cache[channel][-BACKLOG_SIZE:]

def process_message(message_json):
    try:
        if "reply_to" not in message_json:

            # send these messages elsewhere
            known_subtypes = ['channel_join', 'channel_leave', 'channel_topic']
            if "subtype" in message_json and message_json["subtype"] in known_subtypes:
                proc[message_json["subtype"]](message_json)

            else:
                # move message properties down to root of json object
                message_json = unwrap_message(message_json)

                server = servers.find(message_json["myserver"])
                channel = channels.find(message_json["channel"])

                #do not process messages in unexpected channels
                if not channel.active:
                    channel.open(False)
                    dbg("message came for closed channel {}".format(channel.name))
                    return

                cache_message(message_json)

                time = message_json['ts']
                if "fallback" in message_json:
                    text = message_json["fallback"]
                elif "text" in message_json:
                    text = message_json["text"]
                else:
                    text = ""

                text = unfurl_refs(text)
                if "attachments" in message_json:
                    text += u"--- {}".format(unwrap_attachments(message_json))
                text = text.lstrip()
                text = text.replace("\t", "    ")
                name = get_user(message_json, server)

                text = text.encode('utf-8')
                name = name.encode('utf-8')

                channel.buffer_prnt(name, text, time)
        #        server.channels.find(channel).buffer_prnt(name, text, time)
        else:
            if message_json["reply_to"] != None:
                cache_message(message_json)
    except:
        dbg("cannot process message {}".format(message_json))


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


def unfurl_refs(text):
    if text.find('<') > -1:
        newtext = []
        text = text.split(" ")
        for item in text:
            # dbg(item)
            start = item.find('<')
            end = item.find('>')
            if start > -1 and end > -1:
                item = item[start + 1:end]
                if item.find('|') > -1:
                    item = item.split('|')[0]
                if item.startswith('@U'):
                    if users.find(item[1:]):
                        try:
                            item = "@{}".format(users.find(item[1:]).name)
                        except:
                            dbg("NAME: {}".format(item))
                if item.startswith('#C'):
                    if channels.find(item[1:]):
                        item = "{}".format(channels.find(item[1:]).name)
            newtext.append(item)
        text = " ".join(newtext)
        return text
    else:
        return text


def get_user(message_json, server):
    if 'user' in message_json:
        name = server.users.find(message_json['user']).name
    elif 'username' in message_json:
        name = u"-{}-".format(message_json["username"])
    elif 'service_name' in message_json:
        name = u"-{}-".format(message_json["service_name"])
    elif 'bot_id' in message_json:
        name = u"-{}-".format(message_json["bot_id"])
    else:
        name = u""
    return name

# END Websocket handling methods


def typing_bar_item_cb(data, buffer, args):
    typers = [x for x in channels.get_all() if x.is_someone_typing()]
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
        # for channel in channels.find_by_class(Channel) + channels.find_by_class(GroupChannel):
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
                channel.server.send_to_websocket(json.dumps(request))
                typing_timer = now
    return w.WEECHAT_RC_OK

# NOTE: figured i'd do this because they do


def slack_ping_cb(data, remaining):
    servers.find(data).ping()
    return w.WEECHAT_RC_OK


def slack_connection_persistence_cb(data, remaining_calls):
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
            server.send_to_websocket(json.dumps(request))
    return w.WEECHAT_RC_OK

# Slack specific requests

# NOTE: switched to async/curl because sync slowed down the UI


def async_slack_api_request(domain, token, request, post_data, priority=False):
    if not STOP_TALKING_TO_SLACK:
        post_data["token"] = token
        url = 'https://{}/api/{}'.format(domain, request)
        command = 'curl -s --data "{}" {}'.format(urllib.urlencode(post_data), url)
        context = pickle.dumps({"request": request, "token": token, "post_data": post_data})
        w.hook_process(command, 20000, "url_processor_cb", context)

# funny, right?
big_data = {}

def url_processor_cb(data, command, return_code, out, err):
    global big_data, message_cache
    data = pickle.loads(data)
    identifier = sha.sha("{}{}".format(data, command)).hexdigest()
    if identifier not in big_data:
        big_data[identifier] = ''
    big_data[identifier] += out
    if return_code == 0:
        try:
            my_json = json.loads(big_data[identifier])
        except:
            dbg("curl failed, doing again...")
            dbg("curl length: {} identifier {}\n{}".format(len(big_data[identifier]), identifier, data))
            my_json = False

        big_data.pop(identifier, None)

        if my_json:
            if data["request"] == 'rtm.start':
                servers.find(data["token"]).connected_to_slack(my_json)

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
    elif return_code != -1:
        big_data.pop(identifier, None)
        dbg("return code: {}".format(return_code))

    return w.WEECHAT_RC_OK

def cache_write_cb(data, remaining):
    open("{}/{}".format(WEECHAT_HOME, CACHE_NAME), 'w').write(json.dumps(message_cache))
    return w.WEECHAT_RC_OK



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
    global slack_api_token, channels_always_marked_read, channels_not_on_current_server_color, colorize_nicks, slack_debug, debug_mode
    slack_api_token = w.config_get_plugin("slack_api_token")

    if slack_api_token.startswith('${sec.data'):
        slack_api_token = w.string_eval_expression(slack_api_token, {}, {}, {})

    channels_always_marked_read = [x.strip() for x in w.config_get_plugin("channels_always_marked_read").split(',')]
    channels_not_on_current_server_color = w.config_get_plugin("channels_not_on_current_server_color")
    if channels_not_on_current_server_color == "0":
        channels_not_on_current_server_color = False
    colorize_nicks = w.config_get_plugin('colorize_nicks') == "1"
    slack_debug = None
    debug_mode = w.config_get_plugin("debug_mode").lower()
    if debug_mode != '' and debug_mode != 'false':
        create_slack_debug_buffer()
    return w.WEECHAT_RC_OK

def quit_notification_cb(signal, sig_type, data):
    global STOP_TALKING_TO_SLACK
    STOP_TALKING_TO_SLACK = True
    cache_write_cb("", "")

def script_unloaded():
    global STOP_TALKING_TO_SLACK
    STOP_TALKING_TO_SLACK = True
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
        if not w.config_get_plugin('channels_always_marked_read'):
            w.config_set_plugin('channels_always_marked_read', "")
        if not w.config_get_plugin('channels_not_on_current_server_color'):
            w.config_set_plugin('channels_not_on_current_server_color', "0")
        if not w.config_get_plugin('debug_mode'):
            w.config_set_plugin('debug_mode', "")
        if not w.config_get_plugin('colorize_nicks'):
            w.config_set_plugin('colorize_nicks', "1")

        version = w.info_get("version_number", "") or 0
        if int(version) >= 0x00040400:
            legacy_mode = False
        else:
            legacy_mode = True

        # Global var section
        config_changed_cb("", "", "")

        cmds = {k[8:]: v for k, v in globals().items() if k.startswith("command_")}
        proc = {k[8:]: v for k, v in globals().items() if k.startswith("process_")}

        typing_timer = time.time()
        domain = None
        previous_buffer = None
        slack_buffer = None

        buffer_list_update = False
        previous_buffer_list_update = 0

        #name = None
        never_away = False
        hotlist = w.infolist_get("hotlist", "", "")
        main_weechat_buffer = w.info_get("irc_buffer", "{}.{}".format(domain, "DOESNOTEXIST!@#$"))

        try:
            cache_file = open("{}/{}".format(WEECHAT_HOME, CACHE_NAME), 'r')
            message_cache = json.loads(cache_file.read())
        except IOError:
            message_cache = {}
        # End global var section

        #channels = SearchList()
        servers = SearchList()
        for token in slack_api_token.split(','):
            servers.append(SlackServer(token))
        channels = Meta('channels', servers)
        users = Meta('users', servers)

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
        w.hook_command('slack', 'Plugin to allow typing notification and sync of read markers for slack.com', 'stuff', 'stuff2', '|'.join(cmds.keys()), 'slack_command_cb', '')
        w.hook_command('me', '', 'stuff', 'stuff2', '', 'me_command_cb', '')
#        w.hook_command('me', 'me_command_cb', '')
        w.hook_command_run('/join', 'join_command_cb', '')
        w.hook_command_run('/part', 'part_command_cb', '')
        w.hook_command_run('/leave', 'part_command_cb', '')
        w.bar_item_new('slack_typing_notice', 'typing_bar_item_cb', '')
        # END attach to the weechat hooks we need

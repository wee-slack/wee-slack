# -*- coding: utf-8 -*-
#
import time
import json
import sys
import re
import os
import random
import socket
import sha
import thread
import urllib
import urlparse
from websocket import create_connection

import weechat as w

SCRIPT_NAME  = "slack_extension"
SCRIPT_AUTHOR  = "Ryan Huber <rhuber@gmail.com>"
SCRIPT_VERSION = "0.7"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC  = "Extends weechat for typing notification/search/etc on slack.com"

BACKLOG_SIZE = 200

SLACK_API_TRANSLATOR = {
                            "channel": {
                              "history" : "channels.history",
                              "join"    : "channels.join",
                              "leave"   : "channels.leave",
                              "mark"    : "channels.mark"
                            },
                            "im": {
                              "history" : "im.history",
                              "leave"   : "im.close",
                              "mark"    : "im.mark"
                            },
                            "group": {
                              "history" : "groups.history",
                              "join"    : "channels.join",
                              "leave"   : "groups.leave",
                              "mark"    : "groups.mark"
                            }

                       }

def dbg(message):
  w.prnt("", "DEBUG: " + str(message))

#hilarious, i know
class Meta(list):
  def __init__(self, attribute, search_list):
    self.attribute = attribute
    self.search_list = search_list
  def __str__(self):
    string = ''
    for each in self.search_list.get_all(self.attribute):
      string += str(each)
    return string
  def __repr__(self):
    self.search_list.get_all(self.attribute)
  def find(self, name):
    items = self.search_list.find_deep(name, self.attribute)
    items = [x for x in items if x != None]
    if len(items) == 1:
      return items[0]
    elif len(items) == 0:
      pass
    else:
      dbg("probably something bad happened with meta items: %s" % items)
      return items
#      raise AmbiguousProblemError
  def find_by_class(self, class_name):
    #for each in self.search_list.find_by_class(class_name):
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
        if items != None:
          items += child.find_deep(name, attribute)
      elif dir(child).count('find') == 1:
        if items != None:
          items.append(child.find(name, attribute))
    if items != []:
      return items
  def get_all(self, attribute):
    items = []
    for child in self:
      if child.__class__ == self.__class__:
        items += child.get_all(attribute)
      else:
        items += (eval("child."+attribute))
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
        items += (eval('child.'+attribute).find_by_class(class_name))
    return items

class SlackServer(object):
  def __init__(self, token):
    self.nick = None
    self.name = None
    self.domain = None
    self.login_data = None
    self.token = token
    self.ws = None
    self.users = SearchList()
    self.channels = SearchList()
    self.connected = False

    self.identifier = None
    self.connect_to_slack()
    w.hook_timer(6000, 0, 0, "slack_connection_persistence_cb", self.identifier)
  def __eq__(self, compare_str):
    if compare_str == self.identifier or compare_str == self.token:
      return True
    else:
      return False
  def __str__(self):
    return "%s" % (self.identifier)
  def __repr__(self):
    return "%s" % (self.identifier)
  def find(self, name, attribute):
    attribute = eval("self."+attribute)
    return attribute.find(name)
  def connect_to_slack(self):
    data = {}
    t = time.time()
    request = "rtm.start?t=%s" % t
    data["token"] = self.token
    data = urllib.urlencode(data)
    reply = urllib.urlopen('https://slack.com/api/%s' % (request), data)
    if reply.code == 200:
      data = reply.read()
      login_data = json.loads(data)
      if login_data["ok"] == True:
        self.nick = login_data["self"]["name"]
        self.domain = login_data["team"]["domain"] + ".slack.com"
        self.identifier = self.domain
        self.buffer = w.buffer_new(self.domain, "input", "", "", "")

        self.create_slack_websocket(login_data)
        self.create_slack_mappings(login_data)

        self.general_buffer_ptr  = w.buffer_search("",self.domain+".#general")
        nick_ptr = w.nicklist_search_nick(self.general_buffer_ptr,'',self.nick)
        name = w.nicklist_nick_get_string(self.general_buffer_ptr,self.nick,'name')

        self.connected = True
        return True
      else:
        w.prnt("", "\n!! slack.com login error: " + login_data["error"] + "\n Please check your API token with \"/set plugins.var.python.slack_extension.slack_api_token\"\n\n ")
    else:
      self.connected = False
      return False
  def create_slack_websocket(self, data):
    web_socket_url = data['url']
#    try:
    self.ws = create_connection(web_socket_url)
    self.ws.sock.setblocking(0)
    w.hook_fd(self.ws.sock._sock.fileno(), 1, 0, 0, "slack_websocket_cb", self.identifier)
#    except socket.error:
#      return False
    return True
  #  return ws
  def create_slack_mappings(self, data):

    for item in data["users"]:
      self.users.append(User(self, item["name"], item["id"], item["presence"]))

    for item in data["channels"]:
      if not item.has_key("last_read"):
        item["last_read"] = 0
      self.channels.append(Channel(self, item["name"], item["id"], item["is_member"], item["last_read"], "#"))
    for item in data["groups"]:
      if not item.has_key("last_read"):
        item["last_read"] = 0
      self.channels.append(GroupChannel(self, item["name"], item["id"], item["is_open"], item["last_read"], "#"))
    for item in data["ims"]:
      if not item.has_key("last_read"):
        item["last_read"] = 0
      name = self.users.find(item["user"]).name
      self.channels.append(DmChannel(self, name, item["id"], item["is_open"], item["last_read"]))

    for item in self.channels:
      item.get_history()
  def prnt(self, message='no message', user="SYSTEM", backlog=False):
    message = message.encode('ascii', 'ignore')
    if backlog == True:
      tags = "no_highlight,notify_none,logger_backlog_end"
    else:
      tags = ""
    if self.buffer:
      w.prnt_date_tags(self.buffer, 0, tags, "%s\t%s" % (user, message))
    else:
      pass
      #w.prnt("", "%s\t%s" % (user, message))

class SlackThing(object):
  def __init__(self, name, identifier):
    self.name = name
    self.identifier = identifier
    self.channel_buffer = None
  def __str__(self):
    return "Name: %s Id: %s CB: %s" % (self.name, self.identifier, self.channel_buffer)
  def __repr__(self):
    return "Name: %s Id: %s CB: %s" % (self.name, self.identifier, self.channel_buffer)

def input(b,c,data):
  channel = channels.find(b)
  channel.send_message(data)
  channel.prnt(channel.server.nick, data)
  return w.WEECHAT_RC_ERROR

class Channel(SlackThing):
  def __init__(self, server, name, identifier, active, last_read=0, prepend_name=""):
    super(Channel, self).__init__(name, identifier)
    self.type = "channel"
    self.server = server
    self.name = prepend_name + self.name
    self.typing = {}
    self.active = active
    self.last_read = last_read
    if active:
      self.create_buffer()
      self.attach_buffer()
  def __eq__(self, compare_str):
    if compare_str == self.fullname() or compare_str == self.name or compare_str == self.identifier or compare_str == self.name[1:] or (compare_str == self.channel_buffer and self.channel_buffer != None):
      return True
    else:
      return False
  def __str__(self):
    return "Name: %s Id: %s CB: %s Active: %s" % (self.name, self.identifier, self.channel_buffer, self.active)
  def __repr__(self):
    return "Name: %s Id: %s CB: %s Active: %s" % (self.name, self.identifier, self.channel_buffer, self.active)
  def create_buffer(self):
    channel_buffer = w.buffer_search("", "%s.%s" % (self.server.domain, self.name))
    if channel_buffer:
      self.channel_buffer = channel_buffer
    else:
      self.channel_buffer = w.buffer_new("%s.%s" % (self.server.domain, self.name), "input", self.name, "", "")
  def attach_buffer(self):
    channel_buffer = w.buffer_search("", "%s.%s" % (self.server.domain, self.name))
    if channel_buffer != main_weechat_buffer:
      self.channel_buffer = channel_buffer
    else:
      self.channel_buffer = None
  def detach_buffer(self):
    self.channel_buffer = None
    #self.weechat_buffer = None
  def fullname(self):
    return "%s.%s" % (self.server.domain, self.name)
  def set_active(self):
    self.active = True
  def set_inactive(self):
    self.active = False
  def set_typing(self, user):
    self.typing[user] = time.time()
  def send_message(self, message):
    request = {"type":"message","channel":self.identifier, "text": message}
    self.server.ws.send(json.dumps(request))
  def open(self):
    t = time.time() + 1
    async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["join"], {"name":self.name.lstrip("#"),"ts":t})
    self.create_buffer()
    self.active = True
  def close(self):
    t = time.time() + 1
    async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["leave"], {"channel":self.identifier,"ts":t})
    self.active = False
  def unset_typing(self, user):
    try:
      del self.typing[user]
    except:
      pass
  def is_someone_typing(self):
    for user in self.typing.keys():
      if self.typing[user] + 4 > time.time():
        return True
    return False
  def get_typing_list(self):
    typing = []
    for user in self.typing.keys():
      if self.typing[user] + 4 > time.time():
        typing.append(user)
    return typing
  def mark_read(self, update_remote=True):
    self.last_read = 0
    t = time.time() + 1

    if self.channel_buffer:
      w.buffer_set(self.channel_buffer, "unread", "")
    if update_remote:
      async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["mark"], {"channel":self.identifier,"ts":t})
  def rename(self, name=None, fmt=None):
    if self.channel_buffer:
      if name:
        new_name = name
      elif fmt:
        new_name = fmt % (self.name[1:])
      else:
        new_name = self.name
      #w.buffer_set(self.weechat_buffer, "short_name", new_name)
      w.buffer_set(self.channel_buffer, "short_name", new_name)
  def prnt(self, user='unknown user', message='no message', time=0, backlog=False):
    message = message.encode('ascii', 'ignore')
    if backlog == True or (time != 0 and self.last_read > time):
      tags = "no_highlight,notify_none,logger_backlog_end"
    else:
      tags = ""
    time = int(float(time))
    if self.channel_buffer:
      w.prnt_date_tags(self.channel_buffer, time, tags, "%s\t%s" % (user, message))
    else:
      pass
      #w.prnt("", "%s\t%s" % (user, message))
  def get_history(self):
    if self.active:
      t = time.time()
      async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["history"], {"channel":self.identifier,"ts":t, "count":BACKLOG_SIZE, "latest":self.last_read})
      queue.append(self)
      async_slack_api_request(self.server.domain, self.server.token, SLACK_API_TRANSLATOR[self.type]["history"], {"channel":self.identifier,"ts":t, "oldest":self.last_read})

class GroupChannel(Channel):
  def __init__(self, server, name, identifier, active, last_read=0, prepend_name=""):
    super(GroupChannel, self).__init__(server, name, identifier, active, last_read, prepend_name)
    self.type = "group"

class DmChannel(Channel):
  def __init__(self, server, name, identifier, active, last_read=0, prepend_name=""):
    super(DmChannel, self).__init__(server, name, identifier, active, last_read, prepend_name)
    self.type = "im"
  def rename(self, name=None, fmt=None):
    color = w.info_get('irc_nick_color', self.name)
    if self.channel_buffer:
      if name:
        new_name = name
      elif fmt:
        new_name = fmt % (self.name)
      else:
        new_name = self.name
      w.buffer_set(self.channel_buffer, "short_name", color + new_name)

class User(SlackThing):
  def __init__(self, server, name, identifier, presence="away"):
    super(User, self).__init__(name, identifier)
    self.channel_buffer = w.info_get("irc_buffer", "%s.%s" % (domain, self.name))
    self.presence = presence
    self.server = server
  def __eq__(self, compare_str):
    if compare_str == self.name or compare_str == self.identifier:
      return True
    else:
      return False
  def set_active(self):
    self.presence = "active"
  def set_inactive(self):
    self.presence = "away"
  def colorized_name(self):
    color = w.info_get('irc_nick_color', self.name)
    return color+self.name
  def open(self):
    t = time.time() + 1
    #reply = async_slack_api_request("im.open", {"channel":self.identifier,"ts":t})
    async_slack_api_request(self.server.domain, self.server.token, "im.open", {"user":self.identifier,"ts":t})

def slack_command_cb(data, current_buffer, args):
  a = args.split(' ',1)
  if len(a) > 1:
    function_name, args = a[0], " ".join(a[1:])
  else:
    function_name, args = a[0], None
  try:
    cmds[function_name](current_buffer, args)
  except KeyError:
    w.prnt("", "Command not found or exception: "+function_name)
  return w.WEECHAT_RC_OK

def command_talk(current_buffer, args):
  channels.find(current_buffer).server.users.find(args).open()

def command_join(current_buffer, args):
  servers.find(current_domain_name()).channels.find(args).open()

def command_changetoken(current_buffer, args):
  w.config_set_plugin('slack_api_token', args)

def command_test(current_buffer, args):
  if slack_buffer:
    w.prnt(slack_buffer,"worked!")

def command_away(current_buffer, args):
  async_slack_api_request('presence.set', {"presence":"away"})

def command_back(current_buffer, args):
  async_slack_api_request('presence.set', {"presence":"active"})

def command_markread(current_buffer, args):
  #refactor this - one liner i think
  channel = current_buffer_name(short=True)
  domain = current_domain_name()
  if servers.find(domain).channels.find(channel):
    servers.find(domain).channels.find(channel).mark_read()

def command_neveraway(current_buffer, args):
  buf = channels.find(current_buffer).server.buffer
  global never_away
  if never_away == True:
    never_away = False
    w.prnt(buf, "unset never_away")
  else:
    never_away = True
    w.prnt(buf, "set as never_away")

def command_printvar(current_buffer, args):
  w.prnt("", str(eval(args)))

def command_p(current_buffer, args):
  w.prnt("", str(eval(args)))

def command_debug(current_buffer, args):
  create_slack_debug_buffer()

def command_debugstring(current_buffer, args):
  global debug_string
  if args == '':
    debug_string = None
  else:
    debug_string = args

def command_search(current_buffer, args):
  if not slack_buffer:
    create_slack_buffer()
  w.buffer_set(slack_buffer, "display", "1")
  query = args
  w.prnt(slack_buffer,"\nSearched for: %s\n\n" % (query))
  reply = slack_api_request('search.messages', {"query":query}).read()
  data = json.loads(reply)
  for message in data['messages']['matches']:
    message["text"] = message["text"].encode('ascii', 'ignore')
    formatted_message = "%s / %s:\t%s" % (message["channel"]["name"], message['username'], message['text'])
    w.prnt(slack_buffer,str(formatted_message))

def command_nick(current_buffer, args):
  urllib.urlopen("https://%s/account/settings" % (domain))
  browser.select_form(nr=0)
  browser.form['username'] = args
  reply = browser.submit()

### Websocket handling methods

def slack_websocket_cb(data, fd):
  server = data
  try:
    data = servers.find(server).ws.recv()
    message_json = json.loads(data)
    #this magic attaches json that helps find the right dest
    message_json['myserver'] = server
  except:
    return w.WEECHAT_RC_OK
  try:
    if slack_debug != None:
      write_debug(message_json)
  except:
    pass
  #dispatch here
  try:
    function_name = message_json["type"]
    proc[function_name](message_json)
  except KeyError:
    #w.prnt("", "Function not implemented "+function_name)
    pass
  w.bar_item_update("slack_typing_notice")
  return w.WEECHAT_RC_OK

def write_debug(message_json):
  try:
    if message_json.has_key("user"):
      message_json["user"] = users.find(message_json["user"]).name
    if message_json.has_key("channel"):
      message_json["channel"] = channels.find(message_json["channel"]).name
  except:
    pass
  output = "%s" % ( json.dumps(message_json, sort_keys=True) )
  if debug_string:
    if output.find(debug_string) < 0:
      return
  w.prnt(slack_debug,output)

def process_presence_change(message_json):
  #server = servers.find(message_json["myserver"])
#  global nick_ptr
#  if message_json["user"] == nick:
#    nick_ptr = w.nicklist_search_nick(general_buffer_ptr,'',nick)
#    if message_json["presence"] == 'active':
#      w.nicklist_nick_set(general_buffer_ptr, nick_ptr, "prefix", "+")
#    else:
#      w.nicklist_nick_set(general_buffer_ptr, nick_ptr, "prefix", " ")
#  else:
    #this puts +/- in front of usernames in the buffer list. (req buffers.pl)
    buffer_name = "%s.%s" % (domain, message_json["user"])
    buf_ptr  = w.buffer_search("",buffer_name)
    if message_json["presence"] == 'active':
      users.find(message_json["user"]).set_active()
    else:
      users.find(message_json["user"]).set_inactive()

def process_channel_marked(message_json):
  server = servers.find(message_json["myserver"])
  channel = message_json["channel"]
  buffer_name = "%s.%s" % (domain, channel)
  if buffer_name != current_buffer_name():
    buf_ptr  = w.buffer_search("",buffer_name)
    w.buffer_set(buf_ptr, "unread", "")
    #NOTE: only works with latest
    if not legacy_mode:
      w.buffer_set(buf_ptr, "hotlist", "-1")

def process_group_marked(message_json):
  server = servers.find(message_json["myserver"])
  channel = message_json["channel"]
  buffer_name = "%s.%s" % (domain, channel)
  if buffer_name != current_buffer_name():
    buf_ptr  = w.buffer_search("",buffer_name)
    w.buffer_set(buf_ptr, "unread", "")
    #NOTE: only works with latest
    if not legacy_mode:
      w.buffer_set(buf_ptr, "hotlist", "-1")
def process_im_marked(message_json):
  server = servers.find(message_json["myserver"])
  channel = message_json["channel"]
  buffer_name = "%s.%s" % (domain, channel)
  if buffer_name != current_buffer_name():
    buf_ptr  = w.buffer_search("",buffer_name)
    w.buffer_set(buf_ptr, "unread", "")
    #NOTE: only works with latest
    if not legacy_mode:
      w.buffer_set(buf_ptr, "hotlist", "-1")

def process_channel_left(message_json):
  server = servers.find(message_json["myserver"])
  buf = server.channels.find(message_json["channel"]).channel_buffer
  server.channels.find(message_json["channel"]).detach_buffer()
  w.buffer_close(buf)

def process_channel_joined(message_json):
  server = servers.find(message_json["myserver"])
  server.channels.find(message_json["channel"]["id"]).create_buffer()
  server.channels.find(message_json["channel"]["id"]).get_history()

def process_group_close(message_json):
  server = servers.find(message_json["myserver"])
  buf = server.channels.find(message_json["channel"]).channel_buffer
  server.channels.find(message_json["channel"]).detach_buffer()
  try:
    w.buffer_close(buf)
  except:
    pass

def process_group_open(message_json):
  server = servers.find(message_json["myserver"])
  server.channels.find(message_json["channel"]).create_buffer()
  server.channels.find(message_json["channel"]).get_history()
  #buf = server.channels.find(message_json["channel"]).channel_buffer
  #w.buffer_close(buf)

def process_im_close(message_json):
  server = servers.find(message_json["myserver"])
  server.channels.find(message_json["channel"]).set_inactive()
  buf = server.channels.find(message_json["channel"]).channel_buffer
  server.channels.find(message_json["channel"]).detach_buffer()
  try:
    w.buffer_close(buf)
  except:
    pass

def process_im_open(message_json):
  server = servers.find(message_json["myserver"])
  server.channels.find(message_json["channel"]).set_active()
  server.channels.find(message_json["channel"]).create_buffer()
  server.channels.find(message_json["channel"]).get_history()
  #buf = server.channels.find(message_json["channel"]).channel_buffer
  #w.buffer_close(buf)

def process_user_typing(message_json):
  server = servers.find(message_json["myserver"])
  server.channels.find(message_json["channel"]).set_typing(server.users.find(message_json["user"]).name)

#todo: does this work?
def process_error(message_json):
  connected = False

def process_message(message_json):
  server = servers.find(message_json["myserver"])

  mark_silly_channels_read(message_json["channel"])
  channel = message_json["channel"]

#  if message_json.has_key("subtype"):
#    return
  time = message_json["ts"]
  #this handles edits
  try:
    if message_json.has_key("message"):
      message_json["text"] = "Edited: " + message_json["message"]["text"]
      if message_json.has_key("user"):
        message_json["user"] = message_json["message"]["user"]
      elif message_json.has_key("username"):
        message_json["user"] = message_json["message"]["username"]
  except:
    dbg(message_json)

  if message_json.has_key("user") and message_json.has_key("text"):
    #below prevents typing notification from disapearing if the server sends an unfurled message
    server.channels.find(message_json["channel"]).unset_typing(server.users.find(message_json["user"]).name)
    user = server.users.find(message_json["user"]).colorized_name()
    server.channels.find(channel).prnt(user,message_json["text"], time)
  else:
    if message_json.has_key("attachments"):
      if message_json.has_key("username"):
        name = message_json["username"]
      for message in message_json["attachments"]:
        if message.has_key("service_name"):
          name = message["service_name"]
        try:
          server.channels.find(channel).prnt("-%s-" % name,str(message["fallback"]), time)
        except:
          server.channels.find(channel).prnt('unknown user',str(message_json), time)
    else:
      server.channels.find(channel).prnt('unknown user',str(message_json), time)

### END Websocket handling methods

def typing_bar_item_cb(data, buffer, args):
  typers = [x for x in channels if x.is_someone_typing() == True]
  if len(typers) > 0:
    direct_typers = []
    channel_typers = []
    for dm in channels.find_by_class(DmChannel):
      direct_typers.extend(dm.get_typing_list())
    direct_typers = ["D/" + x for x in direct_typers]
    current_channel = current_buffer_name(short=True)
    channel = channels.find(current_channel)
    if channel and channel.__class__ != DmChannel:
      channel_typers = channels.find(current_channel).get_typing_list()
    typing_here = ", ".join(channel_typers + direct_typers)
    if len(typing_here) > 0:
      color = w.color('yellow')
      return color + "typing: " + typing_here
  return ""

def typing_update_cb(data, remaining_calls):
  w.bar_item_update("slack_typing_notice")
  return w.WEECHAT_RC_OK

def buffer_list_update_cb(data, remaining_calls):
  for channel in channels.find_by_class(Channel):
    if channel.is_someone_typing() == True:
      channel.rename(fmt=">%s")
    else:
      channel.rename()
  for channel in channels.find_by_class(GroupChannel):
    if channel.is_someone_typing() == True:
      channel.rename(fmt=">%s")
    else:
      channel.rename()
  for channel in channels.find_by_class(DmChannel):
    if channel.server.users.find(channel.name).presence == "active":
      channel.rename(fmt="+%s")
    else:
      channel.rename(fmt=" %s")
    pass
  return w.WEECHAT_RC_OK

def hotlist_cache_update_cb(data, remaining_calls):
  #this keeps the hotlist dupe up to date for the buffer switch, but is prob technically a race condition. (meh)
  global hotlist
  prev_hotlist = hotlist
  hotlist = w.infolist_get("hotlist", "", "")
  w.infolist_free(prev_hotlist)
  return w.WEECHAT_RC_OK

def buffer_opened_cb(signal, sig_type, data):
  name = w.buffer_get_string(data, "name")
  channel = channels.find(name)
  channel.set_active()
#  domain = ".".join(name.split('.')[:-1])
#  if domain in servers:
  channel.attach_buffer()
  channel.get_history()
#    name = name.split(".")[-1]
#    if server.find(domain).users.find(name):
#      server.find(domain).users.find(name).open()
#    if server.find(domain).channels.find(name):
#      server.find(domain).channels.find(name).attach_buffer()
#      server.find(domain).channels.find(name).get_history()
  return w.WEECHAT_RC_OK

def buffer_closing_cb(signal, sig_type, data):
  if channels.find(data):
    channels.find(data).close()
    channels.find(data).detach_buffer()
  return w.WEECHAT_RC_OK

def buffer_switch_cb(signal, sig_type, data):
  #NOTE: we flush both the next and previous buffer so that all read pointer id up to date
  global previous_buffer, hotlist
  if channels.find(previous_buffer):
    channels.find(previous_buffer).mark_read()

  channel_name = current_buffer_name()
  previous_buffer = data

#  if current_buffer_name().startswith(domain):
#    channel_name = current_buffer_name(short=True)
#    #TESTING ... this code checks to see if there are any unread messages and doesn't reposition the read marker if there are
#    count = 0
#    while w.infolist_next(hotlist):
#      if w.infolist_pointer(hotlist, "buffer_pointer") == w.current_buffer():
#        for i in [0,1,2,3]:
#          count += w.infolist_integer(hotlist, "count_0%s" % (i))
#    if count == 0:
#      if channels.find(previous_buffer):
#        channels.find(previous_buffer).mark_read()
#    #end TESTING
#    previous_buffer = channel_name
#  else:
#    previous_buffer = None
  return w.WEECHAT_RC_OK

def typing_notification_cb(signal, sig_type, data):
  global typing_timer
  now = time.time()
  if typing_timer + 4 < now:
#    try:
#    for server in servers:
    channel = channels.find(current_buffer_name())
    identifier = channel.identifier
    request = {"type":"typing","channel":identifier}
    channel.server.ws.send(json.dumps(request))
    typing_timer = now
#    except:
#      pass
  return w.WEECHAT_RC_OK

#NOTE: figured i'd do this because they do
def slack_ping_cb(data, remaining):
  global counter, connected
  if counter > 999:
    counter = 0
  request = {"type":"ping","id":counter}
  try:
    ws.send(json.dumps(request))
  except:
    connected = False
  counter += 1
  return w.WEECHAT_RC_OK

def slack_connection_persistence_cb(data, remaining_calls):
  if not servers.find(data).connected:
    w.prnt("", "Disconnected from slack, trying to reconnect..")
    servers.find(data).connect_to_slack()
  return w.WEECHAT_RC_OK

def slack_never_away_cb(data, remaining):
  global never_away
  if never_away == True:
    #w.prnt("", 'updating status as back')
    name = channels.find("#general")
    request = {"type":"typing","channel":name}
    ws.send(json.dumps(request))
    #command_back(None)
  return w.WEECHAT_RC_OK

### Slack specific requests

def slack_mark_channel_read(channel_id):
  channel.find(channel_id).mark_read()

#NOTE: switched to async/curl because sync slowed down the UI
def async_slack_api_request(domain, token, request, data):
  t = time.time()
  request += "?t=%s" % t
  data["token"] = token
  data = urllib.urlencode(data)
  post = {"post": "1", "postfields": data}
  url = 'https://%s/api/%s' % (domain, request)
  queue.append(['url:%s' % (url), post, 20000, 'url_processor_cb', str(data)])

#def async_slack_api_request(request, data):
#  t = time.time()
#  request += "?t=%s" % t
#  data["token"] = slack_api_token
#  data = urllib.urlencode(data)
#  command = 'curl --data "%s" https://%s/api/%s' % (data,domain,request)
#  w.hook_process(command, 5000, '', '')

queue = []
url_processor_lock=False
#funny, right?
big_data = {}

def async_queue_cb(data, remaining_calls):
  global url_processor_lock
  if url_processor_lock == False:
    url_processor_lock=True
    if len(queue) > 0:
      item = queue.pop(0)
      try:
        query = urlparse.parse_qs(item[-1])
        if query.has_key("channel") and item[0].find('history') > -1:
          channel = query["channel"][0]
          channel = channels.find(channel)
          channel.server.prnt("downloading channel history for %s" % (channel.name), backlog=True)
      except:
        pass
      if item.__class__ == list:
        #w.hook_process_hashtable(*item)
        command = 'curl --data "%s" %s' % (item[1]["postfields"], item[0][4:])
        w.hook_process(command, 10000, item[3], item[4])
      else:
        item.mark_read(False)
        url_processor_lock=False
    else:
      url_processor_lock=False
  return w.WEECHAT_RC_OK

def url_processor_cb(data, command, return_code, out, err):
  global url_processor_lock, big_data
  url_processor_lock=False
  if return_code == 0:
    url_processor_lock=False
  identifier = sha.sha(str(data) + command).hexdigest()
  if not big_data.has_key(identifier):
    big_data[identifier] = ''
  big_data[identifier] += out
  try:
    my_json = json.loads(big_data[identifier])
  except:
    my_json = False
  if my_json:
    query = urlparse.parse_qs(data)
    if query.has_key("channel"):
      channel = query["channel"][0]
    if query.has_key("token"):
      token = query["token"][0]
    message_json = json.loads(big_data[identifier])
    del big_data[identifier]
    if message_json.has_key("messages"):
      messages = message_json["messages"].reverse()
      for message in message_json["messages"]:
        message["myserver"] = servers.find(token).domain
        message["channel"] = servers.find(token).channels.find(channel)
        process_message(message)
  return w.WEECHAT_RC_OK

#def slack_api_request(request, data):
#  t = time.time()
#  request += "?t=%s" % t
#  data["token"] = slack_api_token
#  data = urllib.urlencode(data)
#  reply = urllib.urlopen('https://%s/api/%s' % (domain, request), data)
#  return reply

def mark_silly_channels_read(channel):
  if channel in channels_always_marked_read:
    if channels.find("channel"):
      channels.find("channel").mark_read()

### END Slack specific requests

### Utility Methods

def current_domain_name():
  buffer = w.current_buffer()
  #number     = w.buffer_get_integer(buffer, "number")
  name = w.buffer_get_string(buffer, "name")
  name = ".".join(name.split(".")[:-1])
  return name

def current_buffer_name(short=False):
  buffer = w.current_buffer()
  #number     = w.buffer_get_integer(buffer, "number")
  name = w.buffer_get_string(buffer, "name")
  if short:
    try:
      name = name.split('.')[-1]
      #name = re.split('\.',name,1)[-1:]
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
  if slack_debug != None:
    w.buffer_set(slack_debug, "display", "1")
  else:
    debug_string = None
    slack_debug = w.buffer_new("slack-debug", "", "", "closed_slack_debug_buffer_cb", "")
    w.buffer_set(slack_debug, "notify", "0")
    w.buffer_set(slack_debug, "display", "1")

### END Utility Methods

# Main
if __name__ == "__main__":
  if w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE,
          SCRIPT_DESC, "", ""):

    if not w.config_get_plugin('server'):
      w.config_set_plugin('server', "slack")
    if not w.config_get_plugin('timeout'):
      w.config_set_plugin('timeout', "4")
    if not w.config_get_plugin('slack_api_token'):
      w.config_set_plugin('slack_api_token', "INSERT VALID KEY HERE!")
    if not w.config_get_plugin('channels_always_marked_read'):
      w.config_set_plugin('channels_always_marked_read', "")

    version = w.info_get("version_number", "") or 0
    if int(version) >= 0x00040400:
      legacy_mode = False
    else:
      legacy_mode = True

    ### Global constants

    DIRECT_MESSAGE = '*direct*'

    ### End global constants

    ### Global var section
    slack_api_token = w.config_get_plugin("slack_api_token")
    #server    = w.config_get_plugin("server")
    timeout   = w.config_get_plugin("timeout")
    channels_always_marked_read = [x.strip() for x in w.config_get_plugin("channels_always_marked_read").split(',')]

    cmds = {k[8:]: v for k, v in globals().items() if k.startswith("command_")}
    proc = {k[8:]: v for k, v in globals().items() if k.startswith("process_")}

    typing_timer        = time.time()
    counter             = 0
    domain              = None
    previous_buffer     = None
    slack_buffer        = None
    slack_debug         = None
    login_data          = None
    nick                = None
    nick_ptr            = None
    name                = None
    connected           = False
    never_away          = False
    hotlist             = w.infolist_get("hotlist", "", "")
    main_weechat_buffer = w.info_get("irc_buffer", "%s.%s" % (domain, "DOESNOTEXIST!@#$"))

    ### End global var section

    #channels            = SearchList()
    servers = SearchList()
    for token in slack_api_token.split(','):
      servers.append(SlackServer(token))
    channels = Meta('channels', servers)
    users = Meta('users', servers)


#    w.hook_timer(60000, 0, 0, "slack_connection_persistence_cb", "")
    w.hook_timer(10, 0, 0, "async_queue_cb", "")

    ### attach to the weechat hooks we need
    w.hook_timer(1000, 0, 0, "typing_update_cb", "")
    w.hook_timer(1000, 0, 0, "buffer_list_update_cb", "")
    w.hook_timer(1000, 0, 0, "hotlist_cache_update_cb", "")
    w.hook_timer(1000 * 3, 0, 0, "slack_ping_cb", "")
    w.hook_timer(1000 * 60* 29, 0, 0, "slack_never_away_cb", "")
    w.hook_signal('buffer_opened', "buffer_opened_cb", "")
    w.hook_signal('buffer_closing', "buffer_closing_cb", "")
    w.hook_signal('buffer_switch', "buffer_switch_cb", "")
    w.hook_signal('window_switch', "buffer_switch_cb", "")
    w.hook_signal('input_text_changed', "typing_notification_cb", "")
    w.hook_command('slack','Plugin to allow typing notification and sync of read markers for slack.com', 'stuff', 'stuff2', '|'.join(cmds.keys()), 'slack_command_cb', '')
    w.bar_item_new('slack_typing_notice', 'typing_bar_item_cb', '')
    ### END attach to the weechat hooks we need


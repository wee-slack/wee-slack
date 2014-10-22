# -*- coding: utf-8 -*-
#
import time
import json
import sys
import re
import os
import socket
import thread
import urllib
from websocket import create_connection

import weechat as w

SCRIPT_NAME  = "slack_extension"
SCRIPT_AUTHOR  = "Ryan Huber <rhuber@gmail.com>"
SCRIPT_VERSION = "0.5"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC  = "Extends weechat for typing notification/search/etc on slack.com"

class SearchList(list):
  def find(self, item):
    try:
      return self[self.index(item)]
    except ValueError:
      return None
  def find_by_class(self, class_name):
    items = []
    for item in self:
      if item.__class__ == class_name:
        items.append(item)
    return items

class SlackThing(object):
  def __init__(self, name, identifier):
    self.name = name
    self.identifier = identifier
  def __eq__(self, compare_str):
    if compare_str == self.name or compare_str == self.identifier or compare_str == self.name[1:]:
      return True
    else:
      return False
  def __str__(self):
    return "Name: %s Id: %s" % (self.name, self.identifier)
  def __repr__(self):
    return "Name: %s Id: %s" % (self.name, self.identifier)

class Channel(SlackThing):
  def __init__(self, name, identifier, prepend_name=""):
    super(Channel, self).__init__(name, identifier)
    self.name = prepend_name + self.name
    self.typing = {}
    weechat_buffer = w.info_get("irc_buffer", "%s,%s" % (server, self.name))
    if weechat_buffer != main_weechat_buffer:
      self.weechat_buffer = weechat_buffer
    else:
      self.weechat_buffer = None
  def set_typing(self, user):
    self.typing[user] = time.time()
  def unset_typing(self, user):
    del self.typing[user]
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
  def mark_read(self):
    t = time.time() + 1
    if self.weechat_buffer:
      w.buffer_set(self.weechat_buffer, "unread", "")
    reply = async_slack_api_request("channels.mark", {"channel":self.identifier,"ts":t})
  def rename(self, name=None, fmt=None):
    if self.weechat_buffer:
      if name:
        new_name = name
      elif fmt:
        new_name = fmt % (self.name[1:])
      else:
        new_name = self.name
      w.buffer_set(self.weechat_buffer, "short_name", new_name)

class GroupChannel(Channel):
  def mark_read(self):
    t = time.time() + 1
    if self.weechat_buffer:
      w.buffer_set(self.weechat_buffer, "unread", "")
    reply = async_slack_api_request("groups.mark", {"channel":self.identifier,"ts":t})

class DmChannel(Channel):
  def mark_read(self):
    t = time.time() + 1
    if self.weechat_buffer:
      w.buffer_set(self.weechat_buffer, "unread", "")
    reply = async_slack_api_request("im.mark", {"channel":self.identifier,"ts":t})
  def rename(self, name=None, fmt=None):
    if self.weechat_buffer:
      if name:
        new_name = name
      elif fmt:
        new_name = fmt % (self.name)
      else:
        new_name = self.name
      w.buffer_set(self.weechat_buffer, "short_name", new_name)

class User(SlackThing):
  def __init__(self, name, identifier, presence="away"):
    super(User, self).__init__(name, identifier)
    self.weechat_buffer = w.info_get("irc_buffer", "%s,%s" % (server, self.name))
    self.presence = presence
  def set_active(self):
    self.presence = "active"
  def set_inactive(self):
    self.presence = "away"

def slack_command_cb(data, current_buffer, args):
  a = args.split(' ',1)
  if len(a) > 1:
    function_name, args = a[0], a[1]
  else:
    function_name, args = a[0], None
#  try:
  cmds[function_name](args)
#  except KeyError:
#    w.prnt("", "Command not found or exception: "+function_name)
  return w.WEECHAT_RC_OK

def command_test(args):
  if slack_buffer:
    w.prnt(slack_buffer,"worked!")

def command_away(args):
  async_slack_api_request('presence.set', {"presence":"away"})

def command_back(args):
  async_slack_api_request('presence.set', {"presence":"active"})

def command_markread(args):
  channel = current_buffer_name(short=True)
  if channels.find(channel):
    channels.find(channel).mark_read()

def command_neveraway(args):
  global never_away
  if never_away == True:
    never_away = False
    w.prnt("", "unset never_away")
  else:
    never_away = True
    w.prnt("", "set as never_away")

def command_printvar(args):
  w.prnt("", str(eval(args)))

def command_debug(args):
  create_slack_debug_buffer()

def command_debugstring(args):
  global debug_string
  if args == '':
    debug_string = None
  else:
    debug_string = args

def command_search(args):
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

def command_awaybomb(args):
  for i in range(1,10):
    async_slack_api_request('presence.set', {"presence":"away"})
    time.sleep(.2)
    async_slack_api_request('presence.set', {"presence":"active"})
    time.sleep(.2)

def command_nick(args):
  urllib.urlopen("https://%s/account/settings" % (domain))
  browser.select_form(nr=0)
  browser.form['username'] = args
  reply = browser.submit()

### Websocket handling methods

def slack_websocket_cb(data, fd):
  try:
    data = ws.recv()
    message_json = json.loads(data)
  except:
    return w.WEECHAT_RC_OK
  try:
    if slack_debug != None:
      write_debug(message_json)
  except:
    pass
  #dispatch here
  function_name = message_json["type"]
  try:
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

#def modify_buffer_name(name, new_name_fmt="%s"):
#  buffer_name = "%s.%s" % (server, name)
#  buf_ptr  = w.buffer_search("",buffer_name)
#  new_buffer_name = new_name_fmt % (name)
#  w.buffer_set(buf_ptr, "short_name", new_buffer_name)

def process_presence_change(data):
  global nick_ptr
  if data["user"] == nick:
    nick_ptr = w.nicklist_search_nick(general_buffer_ptr,'',nick)
    if data["presence"] == 'active':
      w.nicklist_nick_set(general_buffer_ptr, nick_ptr, "prefix", "+")
    else:
      w.nicklist_nick_set(general_buffer_ptr, nick_ptr, "prefix", " ")
  else:
    #this puts +/- in front of usernames in the buffer list. (req buffers.pl)
    buffer_name = "%s.%s" % (server, data["user"])
    buf_ptr  = w.buffer_search("",buffer_name)
    if data["presence"] == 'active':
      users.find(data["user"]).set_active()
    else:
      users.find(data["user"]).set_inactive()

def process_channel_marked(message_json):
  channel = message_json["channel"]
  buffer_name = "%s.%s" % (server, channel)
  if buffer_name != current_buffer_name():
    buf_ptr  = w.buffer_search("",buffer_name)
    w.buffer_set(buf_ptr, "unread", "")
    #NOTE: only works with latest
    if not legacy_mode:
      w.buffer_set(buf_ptr, "hotlist", "-1")

def process_group_marked(message_json):
  channel = message_json["channel"]
  buffer_name = "%s.%s" % (server, channel)
  if buffer_name != current_buffer_name():
    buf_ptr  = w.buffer_search("",buffer_name)
    w.buffer_set(buf_ptr, "unread", "")
    #NOTE: only works with latest
    if not legacy_mode:
      w.buffer_set(buf_ptr, "hotlist", "-1")

def process_im_marked(message_json):
  channel = message_json["channel"]
  buffer_name = "%s.%s" % (server, channel)
  if buffer_name != current_buffer_name():
    buf_ptr  = w.buffer_search("",buffer_name)
    w.buffer_set(buf_ptr, "unread", "")
    #NOTE: only works with latest
    if not legacy_mode:
      w.buffer_set(buf_ptr, "hotlist", "-1")

def process_user_typing(message_json):
  channels.find(message_json["channel"]).set_typing(users.find(message_json["user"]).name)

def process_error(message_json):
  global connected
  connected = False

def process_message(message_json):
  mark_silly_channels_read(message_json["channel"])
  #below prevents typing notification from disapearing if the server sends an unfurled message
  if message_json.has_key("user"):
    channels.find(message_json["channel"]).unset_typing(users.find(message_json["user"]).name)
    user = users.find(message_json["user"]).name
  else:
    user = "unknown user"
  channel = message_json["channel"]
  if message_json["message"].has_key("attachments"):
    attachments = [x["fallback"] for x in message_json["message"]["attachments"]]
    text = "\n".join(attachments)
    text = text.encode('ascii', 'ignore')
  else:
    text = "%s\tEDITED: %s" % (user, message_json["message"]["text"])
    text = text.encode('ascii', 'ignore')
  buffer_name = "%s.%s" % (server, channel)
  if message_json["subtype"] == "message_changed":
    buf_ptr  = w.buffer_search("",buffer_name)
    w.prnt(buf_ptr, text)
  pass

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
  for channel in channels.find_by_class(DmChannel):
    if users.find(channel.name).presence == "active":
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

def buffer_switch_cb(signal, sig_type, data):
  #NOTE: we flush both the next and previous buffer so that all read pointer id up to date
  global previous_buffer, hotlist
  if channels.find(previous_buffer):
    channels.find(previous_buffer).mark_read()

  if current_buffer_name().startswith(server):
    channel_name = current_buffer_name(short=True)
    #TESTING ... this code checks to see if there are any unread messages and doesn't reposition the read marker if there are
    count = 0
    while w.infolist_next(hotlist):
      if w.infolist_pointer(hotlist, "buffer_pointer") == w.current_buffer():
        for i in [0,1,2,3]:
          count += w.infolist_integer(hotlist, "count_0%s" % (i))
    if count == 0:
      if channels.find(previous_buffer):
        channels.find(previous_buffer).mark_read()
    #end TESTING
    previous_buffer = channel_name
  else:
    previous_buffer = None
  return w.WEECHAT_RC_OK

def typing_notification_cb(signal, sig_type, data):
  global typing_timer
  now = time.time()
  if typing_timer + 4 < now:
    try:
      identifier = channels.find(current_buffer_name(True)).identifier
      request = {"type":"typing","channel":identifier}
      ws.send(json.dumps(request))
      typing_timer = now
    except:
      pass
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
  global connected
  if not connected:
    w.prnt("", "Disconnected from slack, trying to reconnect..")
    connect_to_slack()
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

def connect_to_slack():
  global login_data, nick, connected, general_buffer_ptr, nick_ptr, name, domain
  data = {}
  t = time.time()
  request = "rtm.start?t=%s" % t
  data["token"] = slack_api_token
  data = urllib.urlencode(data)
  reply = urllib.urlopen('https://slack.com/api/%s' % (request), data)
  if reply.code == 200:
    data = reply.read()
    login_data = json.loads(data)
    if login_data["ok"] == True:
      nick = login_data["self"]["name"]
      domain = login_data["team"]["domain"] + ".slack.com"

      create_slack_mappings(login_data)
      create_slack_websocket(login_data)

      general_buffer_ptr  = w.buffer_search("",server+".#general")
      nick_ptr = w.nicklist_search_nick(general_buffer_ptr,'',nick)
      name = w.nicklist_nick_get_string(general_buffer_ptr,nick,'name')

#      set_initial_statii(login_data["users"])

      connected = True
      return True
    else:
      w.prnt("", "\n!! slack.com login error: " + login_data["error"] + "\n Please check your API token with \"/set plugins.var.python.slack_extension.slack_api_token\"\n\n ")
  else:
    connected = False
    return False

#def set_initial_statii(data):
#  for user in users:
#    if user.presence == "active":
#      modify_buffer_name(user["name"], "!%s")
#    else:
#      modify_buffer_name(user["name"], " %s")

def create_slack_mappings(data):
  global users, channels
  users = SearchList()
  channels = SearchList()

  for item in data["users"]:
    users.append(User(item["name"], item["id"], item["presence"]))

  for item in data["channels"]:
    channels.append(Channel(item["name"], item["id"], "#"))
  for item in data["groups"]:
    channels.append(GroupChannel(item["name"], item["id"], "#"))
  for item in data["ims"]:
    name = users.find(item["user"]).name
    channels.append(DmChannel(name, item["id"]))

def create_slack_websocket(data):
  global ws
  web_socket_url = data['url']
  try:
    ws = create_connection(web_socket_url)
    ws.sock.setblocking(0)
    w.hook_fd(ws.sock._sock.fileno(), 1, 0, 0, "slack_websocket_cb", "")
  except socket.error:
    return False
  return True
#  return ws

#NOTE: switched to async/curl because sync slowed down the UI
def async_slack_api_request(request, data):
  t = time.time()
  request += "?t=%s" % t
  data["token"] = slack_api_token
  data = urllib.urlencode(data)
  command = 'curl --data "%s" https://%s/api/%s' % (data,domain,request)
  w.hook_process(command, 5000, '', '')
  return True

def slack_api_request(request, data):
  t = time.time()
  request += "?t=%s" % t
  data["token"] = slack_api_token
  data = urllib.urlencode(data)
  reply = urllib.urlopen('https://%s/api/%s' % (domain, request), data)
  return reply

def mark_silly_channels_read(channel):
  if channel in channels_always_marked_read:
    channels.find("channel").mark_read()

### END Slack specific requests

### Utility Methods

def current_buffer_name(short=False):
  buffer = w.current_buffer()
  #number     = w.buffer_get_integer(buffer, "number")
  name = w.buffer_get_string(buffer, "name")
  if short:
    try:
      name = re.split('\.',name,1)[1]
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
    server    = w.config_get_plugin("server")
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
    general_buffer_ptr  = None
    name                = None
    channels            = []
    connected           = False
    never_away          = False
    hotlist             = w.infolist_get("hotlist", "", "")
    main_weechat_buffer = w.info_get("irc_buffer", "%s,%s" % (server, "DOESNOTEXIST!@#$"))

    ### End global var section

    connect_to_slack()

    w.hook_timer(60000, 0, 0, "slack_connection_persistence_cb", "")

    ### attach to the weechat hooks we need
    w.hook_timer(1000, 0, 0, "typing_update_cb", "")
    w.hook_timer(1000, 0, 0, "buffer_list_update_cb", "")
    w.hook_timer(1000, 0, 0, "hotlist_cache_update_cb", "")
    w.hook_timer(1000 * 3, 0, 0, "slack_ping_cb", "")
    w.hook_timer(1000 * 60* 29, 0, 0, "slack_never_away_cb", "")
    w.hook_signal('buffer_switch', "buffer_switch_cb", "")
    w.hook_signal('window_switch', "buffer_switch_cb", "")
    w.hook_signal('input_text_changed', "typing_notification_cb", "")
    w.hook_command('slack','Plugin to allow typing notification and sync of read markers for slack.com', 'stuff', 'stuff2', '|'.join(cmds.keys()), 'slack_command_cb', '')
    w.bar_item_new('slack_typing_notice', 'typing_bar_item_cb', '')
    ### END attach to the weechat hooks we need


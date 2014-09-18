# -*- coding: utf-8 -*-
#
import time
import json
import re
import socket
import urllib
from websocket import create_connection

import weechat as w

SCRIPT_NAME  = "slack_extension"
SCRIPT_AUTHOR  = "Ryan Huber <rhuber@gmail.com>"
SCRIPT_VERSION = "0.3"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC  = "Extends weechat for typing notification/search/etc on slack.com"

typing = {}

def slack_command_cb(data, current_buffer, args):
  a = args.split(' ',1)
  if len(a) > 1:
    function_name, args = a[0], a[1]
  else:
    function_name, args = a[0], None
  try:
    cmds[function_name](args)
  except KeyError:
    w.prnt("", "Command not found or exception: "+function_name)
  return w.WEECHAT_RC_OK

def command_test(args):
  if slack_buffer:
    w.prnt(slack_buffer,"worked!")

def command_away(args):
  async_slack_api_request('presence.set', {"presence":"away"})

def command_back(args):
  async_slack_api_request('presence.set', {"presence":"active"})

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

def slack_cb(data, fd):
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
  dereference_hash(message_json)
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
  dereference_hash(message_json)
  output = "%s" % ( json.dumps(message_json, sort_keys=True) )
  if debug_string:
    if output.find(debug_string) < 0:
      return
  w.prnt(slack_debug,output)

def process_presence_change(data):
  global nick_ptr
  if data["user"] == nick:
    nick_ptr = w.nicklist_search_nick(general_buffer_ptr,'',nick)
    if data["presence"] == 'active':
      w.nicklist_nick_set(general_buffer_ptr, nick_ptr, "prefix", "+")
    else:
      w.nicklist_nick_set(general_buffer_ptr, nick_ptr, "prefix", " ")
  else:
    pass

def process_channel_marked(message_json):
  channel = message_json["channel"]
  buffer_name = "%s.#%s" % (current_server_name(), channel)
  if buffer_name != current_buffer_name():
    buf_ptr  = w.buffer_search("",buffer_name)
    w.buffer_set(buf_ptr, "unread", "")
    #NOTE: only works with latest
    if not legacy_mode:
      w.buffer_set(buf_ptr, "hotlist", "-1")

def process_im_marked(message_json):
  channel = message_json["channel"]
  buffer_name = "%s.%s" % (current_server_name(), channel.lstrip('DM/'))
  if buffer_name != current_buffer_name():
    buf_ptr  = w.buffer_search("",buffer_name)
    w.buffer_set(buf_ptr, "unread", "")
    #NOTE: only works with latest
    if not legacy_mode:
      w.buffer_set(buf_ptr, "hotlist", "-1")

def process_message(message_json):
  chan_and_user = message_json["channel"] + ":" + message_json["user"]
  if typing.has_key(chan_and_user):
    del typing[chan_and_user]

def process_user_typing(message_json):
  typing[message_json["channel"] + ":" + message_json["user"]] = time.time()

def process_error(message_json):
  global connected
  connected = False

def process_message(message_json):
  channel = message_json["channel"]
  user = user_hash[message_json["message"]["user"]]
  if message_json["message"].has_key("attachments"):
    text = message_json["message"]["attachments"][0]["fallback"]
    text = text.encode('ascii', 'ignore')
  else:
    text = "%s\tEDITED: %s" % (user, message_json["message"]["text"])
    text = text.encode('ascii', 'ignore')
  if channel.startswith('DM/'):
    buffer_name = "%s.%s" % (current_server_name(), channel[3:])
  else:
    buffer_name = "%s.#%s" % (current_server_name(), channel)
  if message_json["subtype"] == "message_changed":
    buf_ptr  = w.buffer_search("",buffer_name)
    w.prnt(buf_ptr, text)
  pass

### END Websocket handling methods

def typing_bar_item_cb(data, buffer, args):
  if typing:
    #TODO: make this a config option
    color = w.color('yellow')
    typing_here = []
    for chan_and_user in typing.keys():
      chan, user = chan_and_user.split(":")
      if chan.startswith("DM/"):
        typing_here.append("d/"+user)
      else:
        if current_buffer_name() == "%s.#%s" % (current_server_name(), chan):
          typing_here.append(user)
          pass
    if len(typing_here) > 0:
      return color + "typing: " + ", ".join(typing_here)
  return ""

def typing_update_cb(data, remaining_calls):
  for chan_and_user in typing.keys():
    if typing[chan_and_user] < time.time() - 5:
      del typing[chan_and_user]
      w.bar_item_update("slack_typing_notice")
  return w.WEECHAT_RC_OK


def buffer_switch_cb(signal, sig_type, data):
  #NOTE: we flush both the next and previous buffer so that all read pointer id up to date
  global previous_buffer
#  w.prnt("",str(previous_buffer))
  if reverse_channel_hash.has_key(previous_buffer):
    slack_mark_channel_read(reverse_channel_hash[previous_buffer])
  if current_buffer_name().startswith(current_server_name()):
    channel_name = current_buffer_name(short=True)
    if reverse_channel_hash.has_key(channel_name):
      slack_mark_channel_read(reverse_channel_hash[channel_name])
      previous_buffer = channel_name
  else:
    previous_buffer = None
  return w.WEECHAT_RC_OK

def keep_channel_read_cb(data, remaining):
#TODO move this
  for each in ["client_events","events"]:
    if reverse_channel_hash.has_key(each):
      slack_mark_channel_read(reverse_channel_hash[each])
  return w.WEECHAT_RC_OK

def typing_notification_cb(signal, sig_type, data):
  global timer
  now = time.time()
  if timer + 4 < now:
    name = current_buffer_name()
    try:
      srv, channel_name = re.split('\.#?',name,1)
      if reverse_channel_hash.has_key(channel_name) and srv == current_server_name():
        name = reverse_channel_hash[channel_name]
        request = {"type":"typing","channel":name}
        ws.send(json.dumps(request))
        #w.prnt("",json.dumps(request))
      timer = now
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
    connect_all_to_slack()
  return w.WEECHAT_RC_OK

def slack_never_away_cb(data, remaining):
  global never_away
  if never_away == True:
    #w.prnt("", 'updating status as back')
    name = reverse_channel_hash["general"]
    request = {"type":"typing","channel":name}
    ws.send(json.dumps(request))
    #command_back(None)
  return w.WEECHAT_RC_OK

### Slack specific requests

def slack_api_token(servername):
  key = "%s.slack_api_token" % servername
  return w.config_get_plugin(key)

def current_server_name():
  current_buffer = w.current_buffer()
  name = w.buffer_get_string(current_buffer, "name")
  name_parts = name.split(".")
  if len(name_parts) < 2:
    return ""

  return name_parts[0]

def slack_mark_channel_read(channel_id):
  t = int(time.time())
  if channel_id.startswith('C'):
    reply = async_slack_api_request("channels.mark", {"channel":channel_id,"ts":t})
  elif channel_id.startswith('D'):
    reply = async_slack_api_request("im.mark", {"channel":channel_id,"ts":t})

def connect_all_to_slack():
  for server in enabled_servers():
    connect_to_slack(server)

def connect_to_slack(servername):
  global login_data, nick, connected, general_buffer_ptr, nick_ptr, name, domain
  data = {}
  t = int(time.time())
  request = "users.login?t=%s" % t
  data["token"] = slack_api_token(servername)
  data = urllib.urlencode(data)
  reply = urllib.urlopen('https://slack.com/api/%s' % (request), data)
  if reply.code == 200:
    data = reply.read()
    login_data = json.loads(data)
    if login_data["ok"] == True:
      nick = login_data["self"]["name"]
      domain = login_data["team"]["domain"] + ".slack.com"

      create_slack_lookup_hashes(login_data)
      create_slack_websocket(login_data)

      general_buffer_ptr  = w.buffer_search("",current_server_name()+".#general")
      nick_ptr = w.nicklist_search_nick(general_buffer_ptr,'',nick)
      name = w.nicklist_nick_get_string(general_buffer_ptr,nick,'name')

      connected = True
      return True
    else:
      w.prnt("", "\n!! slack.com login error: " + login_data["error"] + "\n Please check your API token with \"/set plugins.var.python.slack_extension.%s.slack_api_token\"\n\n " % servername)
  else:
    connected = False
    return False

def create_slack_lookup_hashes(login_data):
  global user_hash, channel_hash, reverse_channel_hash
  user_hash = create_user_hash(login_data)
  channel_hash = create_channel_hash(login_data)
  reverse_channel_hash = create_reverse_channel_hash(login_data)

def create_slack_websocket(data):
  global ws
  web_socket_url = data['url']
  try:
    ws = create_connection(web_socket_url)
    ws.sock.setblocking(0)
    w.hook_fd(ws.sock._sock.fileno(), 1, 0, 0, "slack_cb", "")
  except socket.error:
    return False
  return True
#  return ws

#NOTE: switched to async/curl because sync slowed down the UI
def async_slack_api_request(request, data):
  t = int(time.time())
  request += "?t=%s" % t
  data["token"] = slack_api_token(current_server_name())
  data = urllib.urlencode(data)
  command = 'curl --data "%s" https://%s/api/%s' % (data,domain,request)
  w.hook_process(command, 5000, '', '')
  return True

def slack_api_request(request, data):
  t = int(time.time())
  request += "?t=%s" % t
  data["token"] = slack_api_token(current_server_name())
  data = urllib.urlencode(data)
  reply = urllib.urlopen('https://%s/api/%s' % (domain, request), data)
  return reply

def dereference_hash(data):
  try:
    if data.has_key("user"):
      data["user"] = user_hash[data["user"]]
    if data.has_key("channel"):
      data["channel"] = channel_hash[data["channel"]]
  except:
    pass

def create_user_hash(data):
  blah = {}
  for item in data["users"]:
    blah[item["id"]] = item["name"]
  return blah

def create_channel_hash(data):
  blah = {}
  for item in data["channels"]:
    blah[item["id"]] = item["name"]
  for item in data["ims"]:
    blah[item["id"]] = "DM/" + user_hash[item["user"]]
  return blah

def create_reverse_channel_hash(data):
  blah = {}
  for item in data["channels"]:
    blah[item["name"]] = item["id"]
  for item in data["ims"]:
    blah[user_hash[item["user"]]] = item["id"]
  return blah

### END Slack specific requests

### Utility Methods

def current_buffer_name(short=False):
  buffer = w.current_buffer()
  #number     = w.buffer_get_integer(buffer, "number")
  name = w.buffer_get_string(buffer, "name")
  if short:
    try:
      name = re.split('\.#?',name,1)[1]
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

def enabled_servers():
  servers = w.config_get_plugin("servers")
  return map(str.strip, servers.split(","))

### END Utility Methods

# Main
if __name__ == "__main__":
  if w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE,
          SCRIPT_DESC, "", ""):

    if not w.config_get_plugin('servers'):
      w.config_set_plugin('servers', "")
    if not w.config_get_plugin('timeout'):
      w.config_set_plugin('timeout', "4")

    version = w.info_get("version_number", "") or 0
    if int(version) >= 0x00040400:
      legacy_mode = False
    else:
      legacy_mode = True

    ### Global var section
    timeout   = w.config_get_plugin("timeout")

    cmds = {k[8:]: v for k, v in globals().items() if k.startswith("command_")}
    proc = {k[8:]: v for k, v in globals().items() if k.startswith("process_")}

    timer               = time.time()
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
    connected           = False
    never_away          = False

    ### End global var section

    connect_all_to_slack()

    w.hook_timer(60000, 0, 0, "slack_connection_persistence_cb", "")

    ### attach to the weechat hooks we need
    w.hook_timer(1000, 0, 0, "typing_update_cb", "")
    w.hook_timer(1000 * 60, 0, 0, "keep_channel_read_cb", "")
    w.hook_timer(1000 * 3, 0, 0, "slack_ping_cb", "")
    w.hook_timer(1000 * 60* 29, 0, 0, "slack_never_away_cb", "")
    w.hook_signal('buffer_switch', "buffer_switch_cb", "")
    w.hook_signal('window_switch', "buffer_switch_cb", "")
    w.hook_signal('input_text_changed', "typing_notification_cb", "")
    w.hook_command('slack','Plugin to allow typing notification and sync of read markers for slack.com', 'stuff', 'stuff2', '|'.join(cmds.keys()), 'slack_command_cb', '')
    w.bar_item_new('slack_typing_notice', 'typing_bar_item_cb', '')
    ### END attach to the weechat hooks we need

# vim:sw=2:ts=2

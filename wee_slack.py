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
#import requests
import mechanize
from websocket import create_connection

import weechat as w
import re

SCRIPT_NAME  = "slack_extension"
SCRIPT_AUTHOR  = "Ryan Huber <rhuber@gmail.com>"
SCRIPT_VERSION = "0.1"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC  = "Extends weechat for typing notification/search/etc on slack.com"

typing = {}

def slack_command_cb(data, current_buffer, args):
  if args == "away":
    async_slack_api_request(None, 'presence.set', {"presence":"away"})
  elif args == "back":
    async_slack_api_request(None, 'presence.set', {"presence":"active"})
  elif args.startswith("search"):
    query = args.split(' ',1)[1]
    w.prnt('',"\nSearched for: %s\n\n" % (query))
    reply = slack_api_request(browser, 'search.messages', {"query":query}).read()
    data = json.loads(reply)
    #w.prnt('',str(data))
    for message in data['messages']['matches']:
      message["text"] = message["text"].encode('ascii', 'ignore')
      formatted_message = "%s / %s:\t%s" % (message["channel"]["name"], message['username'], message['text'])
      w.prnt('',str(formatted_message))
  elif args == "awaybomb":
    for i in range(1,10):
      async_slack_api_request(None, 'presence.set', {"presence":"away"})
      time.sleep(.2)
      async_slack_api_request(None, 'presence.set', {"presence":"active"})
      time.sleep(.2)
  elif args == "nickup":
    import random
    import string
    times = 26
    for i in range(0,times):
      browser.open("https://%s/account/settings" % (domain))
      browser.select_form(nr=0)
      if i != (times - 1):
        name = string.ascii_lowercase[i]
        #name = ''.join(random.choice(string.ascii_lowercase) for _ in range(10))
      else:
        name = nick
      browser.form['username'] = name
      reply = browser.submit()
  elif args.startswith("nickup2"):
    text = args.split()[1:]
    for s in text:
      browser.open("https://%s/account/settings" % (domain))
      browser.select_form(nr=0)
      name = s
      browser.form['username'] = "a---" + name
      reply = browser.submit()
    browser.open("https://%s/account/settings" % (domain))
    browser.select_form(nr=0)
    browser.form['username'] = nick
    reply = browser.submit()
  elif args.startswith("nickup3"):
    text = user_hash.values()
    for s in text:
      browser.open("https://%s/account/settings" % (domain))
      browser.select_form(nr=0)
      name = "cyber"+s
      browser.form['username'] = name
      reply = browser.submit()
    browser.open("https://%s/account/settings" % (domain))
    browser.select_form(nr=0)
    browser.form['username'] = nick
    reply = browser.submit()
  return w.WEECHAT_RC_OK

def slack_cb(data, fd):
  try:
    data = ws.recv()
    #w.prnt("",data)
    #data =
    message_json = json.loads(data)
  except:
    return w.WEECHAT_RC_OK
  dereference_hash(message_json)
  #dispatch here
  function_name = "process_"+message_json["type"]
  try:
    eval(function_name)(message_json)
  except:
    #w.prnt("", "Function not implemented "+function_name)
    pass

  w.bar_item_update("slack_typing_notice")
  return w.WEECHAT_RC_OK

def process_presence_change(data):
  if data["user"] == nick:
    if data["presence"] == 'active':
      w.nicklist_nick_set(general_buffer_ptr, nick_ptr, "prefix", "+")
    else:
      w.nicklist_nick_set(general_buffer_ptr, nick_ptr, "prefix", " ")
  else:
    pass

def process_channel_marked(message_json):
  channel = message_json["channel"]
  buffer_name = "%s.#%s" % (server, channel)
  if buffer_name != current_buffer_name():
    buf_ptr  = w.buffer_search("",buffer_name)
    w.buffer_set(buf_ptr, "unread", "")
    #NOTE: only works with latest
    w.buffer_set(buf_ptr, "hotlist", "-1")

def process_im_marked(message_json):
  channel = message_json["channel"]
  buffer_name = "%s.%s" % (server, channel.lstrip('DM/'))
  if buffer_name != current_buffer_name():
    buf_ptr  = w.buffer_search("",buffer_name)
    w.buffer_set(buf_ptr, "unread", "")
    #NOTE: only works with latest
    w.buffer_set(buf_ptr, "hotlist", "-1")

def process_message(message_json):
  chan_and_user = message_json["channel"] + ":" + message_json["user"]
  if typing.has_key(chan_and_user):
    del typing[chan_and_user]

def process_user_typing(message_json):
  typing[message_json["channel"] + ":" + message_json["user"]] = time.time()

def typing_bar_item_cb(data, buffer, args):
  if typing:
    typing_here = []
    for chan_and_user in typing.keys():
      chan, user = chan_and_user.split(":")
      if chan.startswith("DM/"):
        typing_here.append("d/"+user)
      else:
        if current_buffer_name() == "%s.#%s" % (server, chan):
          typing_here.append(user)
          pass
    if len(typing_here) > 0:
      return "typing: " + ", ".join(typing_here)
  return ""

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

def typing_update_cb(data, remaining_calls):
  for chan_and_user in typing.keys():
    if typing[chan_and_user] < time.time() - 5:
      del typing[chan_and_user]
      w.bar_item_update("slack_typing_notice")
  return w.WEECHAT_RC_OK

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

def create_browser_instance():
  browser = mechanize.Browser()
  browser.set_handle_robots(False)
  return browser

def buffer_switch_cb(signal, sig_type, data):
  #NOTE: we flush both the next and previous buffer so that all read pointer id up to date
  global previous_buffer
#  w.prnt("",str(previous_buffer))
  if reverse_channel_hash.has_key(previous_buffer):
    slack_mark_channel_read(reverse_channel_hash[previous_buffer])
  if current_buffer_name().startswith(server):
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
      if reverse_channel_hash.has_key(channel_name) and srv == server:
        name = reverse_channel_hash[channel_name]
        request = {"type":"typing","channel":name}
        ws.send(json.dumps(request))
        #w.prnt("",json.dumps(request))
      timer = now
    except:
      pass
  return w.WEECHAT_RC_OK

def slack_mark_channel_read(channel_id):
  t = int(time.time())
  if channel_id.startswith('C'):
    reply = async_slack_api_request(browser, "channels.mark", {"channel":channel_id,"ts":t})
  elif channel_id.startswith('D'):
    reply = async_slack_api_request(browser, "im.mark", {"channel":channel_id,"ts":t})

#NOTE: switched to async/curl because sync slowed down the UI
def async_slack_api_request(browser, request, data):
  t = int(time.time())
  request += "?t=%s" % t
  data["token"] = stuff["api_token"]
  data = urllib.urlencode(data)
  command = 'curl --data "%s" https://%s/api/%s' % (data,domain,request)
  w.hook_process(command, 5000, '', '')
  return True

def slack_api_request(browser, request, data):
  t = int(time.time())
  request += "?t=%s" % t
  data["token"] = stuff["api_token"]
  data = urllib.urlencode(data)
  reply = browser.open('https://%s/api/%s' % (domain, request), data)
  return reply

def connect_to_slack(browser):
  browser.open('https://%s' % (domain))
  browser.select_form(nr=0)
  browser.form['email'] = email
  browser.form['password'] = password
  reply = browser.submit()
  #TODO: this is pretty hackish, i am grabbing json from an html comment
  if reply.code == 200:
    data = reply.read()
    n = data.split('var boot_data = {')[1]
    n = n.split("TS.boot(boot_data)")[0]
    n = re.split('[\n\t]', n)
    settings = filter(None, n)
    setting_hash = {}
    for setting in settings:
      name, setting = re.split('[^\w{[\']+',setting, 1)
      setting_hash[name] = setting.lstrip("'").rstrip(",'")
    return setting_hash
  else:
    stuff = None

def create_slack_websocket(data):
  web_socket_url = data['url']
  ws = create_connection(web_socket_url)
  ws.sock.setblocking(0)
  return ws

# Main
if __name__ == "__main__":
  if w.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE,
          SCRIPT_DESC, "", ""):

    if not w.config_get_plugin('email'):
      w.config_set_plugin('email', "user@example.com")
    if not w.config_get_plugin('password'):
      w.config_set_plugin('password', 'mypassword')
    if not w.config_get_plugin('domain'):
      w.config_set_plugin('domain', "example.slack.com")
    if not w.config_get_plugin('server'):
      w.config_set_plugin('server', "slack")
    if not w.config_get_plugin('timeout'):
      w.config_set_plugin('timeout', "4")

    email     = w.config_get_plugin("email")
    password  = w.config_get_plugin("password")
    domain    = w.config_get_plugin("domain")
    server    = w.config_get_plugin("server")
    timeout   = w.config_get_plugin("timeout")

    timer = time.time()
    previous_buffer = None

    browser = create_browser_instance()
    stuff = connect_to_slack(browser)
    login_data = json.loads(stuff['login_data'])
    nick = login_data["self"]["name"]
    #w.prnt("", str(login_data["self"]))

    general_buffer_ptr  = w.buffer_search("",server+".#general")
    nick_ptr            = w.nicklist_search_nick(general_buffer_ptr,'',nick)
    name = w.nicklist_nick_get_string(general_buffer_ptr,nick,'name')


    if stuff != None:
      user_hash = create_user_hash(login_data)
      channel_hash = create_channel_hash(login_data)
      reverse_channel_hash = create_reverse_channel_hash(login_data)
      ws = create_slack_websocket(login_data)
      w.hook_fd(ws.sock._sock.fileno(), 1, 0, 0, "slack_cb", "")
      w.hook_timer(1000, 0, 0, "typing_update_cb", "")
      w.hook_timer(1000 * 60, 0, 0, "keep_channel_read_cb", "")
      w.hook_signal('buffer_switch', "buffer_switch_cb", "")
      w.hook_signal('window_switch', "buffer_switch_cb", "")
      w.hook_signal('input_text_changed', "typing_notification_cb", "")
      w.hook_command('slack','Plugin to allow typing notification and sync of read markers for slack.com', 'stuff', 'stuff2', 'search|nickup|nickup2|nickup3|awaybomb', 'slack_command_cb', '')
      w.bar_item_new('slack_typing_notice', 'typing_bar_item_cb', '')
    else:
      w.prnt("", 'You need to configure this plugin!')


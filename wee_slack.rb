# Install instructions:
# ---------------------
#
# This script requires your Weechat to be built with ruby.
#
# Load into Weechat like any other plugin, after putting it into
# your ~/.weechat/ruby directory:
#
#      /script load wee_slack.rb
#
require 'rubygems'

module SlackCommands
  def debug(*args)
    Weechat.print("", "hello from the wee_slack plugin")
  end

  def slack(data, buffer, args)
    arguments = args.split(" ")
    begin
      method = arguments.shift
      send(method, arguments)
    rescue => e
      Weechat.print("sorry:", "The Slack plugin doesn't understand that command")
    end
  end

  def help(args)
    Weechat.print("help: ", "Availble commands are: 'help' | 'debug'")
  end
end

extend SlackCommands
include SlackCommands

SIGNATURE = [
  'wee_slack',
  'Ryan Huber <rhuber@gmail.com>, Mike Krisher <mkrisher@gmail.com>',
  '0.1',
  'MIT',
  'Extends weechat for typing notification/search/etc on slack.com',
  'weechat_unload',
  'UTF-8'
]

def weechat_init
  Weechat::register *SIGNATURE
  define_hooks
  return Weechat::WEECHAT_RC_OK
end

def define_hooks
  Weechat.hook_command(
    'slack', # name
    'Plugin to allow typing notification and sync of read markers for slack.com',
    '[list]',
    'description of arguments',
    SlackCommands.methods().join("|"),
    'slack',
    '')
end

def weechat_unload
  return Weechat::WEECHAT_RC_OK
end

__END__
# donate to weechat: http://weechat.org/about/donate/


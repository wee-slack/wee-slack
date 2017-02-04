from mock import Mock
#from wee_slack import SlackChannel

def test_SlackChannel(realish_eventrouter):
    e = realish_eventrouter

    print e.sc["team"].channels
    #c = SlackChannel(e, **json.loads(chan))
    c = e.sc["team"].channels['C3ZEQAYN7']

    print c.formatted_name()
    c.is_someone_typing = Mock(return_value=True)
    c.channel_buffer = Mock(return_value=True)
    print c.create_buffer()
    print c.rename()
    print c.current_short_name
    print c.formatted_name()
    print c.rename()
    print c.formatted_name()

    print "-------"
    print c == "random"
    print "-------"
    print c == "#random"
    print "-------"
    print c == "weeslacktest.slack.com.#random"
    print "-------"
    print c == "weeslacktest.slack.com.random"
    print "-------"
    print c == "dandom"

    print e.weechat_controller.buffers
    #assert False

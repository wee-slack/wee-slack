from __future__ import print_function

from mock import Mock
#from wee_slack import SlackChannel

def test_SlackGroupChannel(realish_eventrouter):
    e = realish_eventrouter

    print(e.sc["team"].channels)
    #c = SlackChannel(e, **json.loads(chan))
    c = e.sc["team"].channels['G3ZJKP7GA']

    print(c.formatted_name())
    c.is_someone_typing = Mock(return_value=True)
    c.channel_buffer = Mock(return_value=True)
    print(c.create_buffer())
    print(c.rename())
    print(c.current_short_name)
    print(c.formatted_name())
    print(c.rename())
    print(c.formatted_name())
#    assert False

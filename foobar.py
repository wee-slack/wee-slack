import sys
sys.path.append('./_pytest')
from conftest import FakeWeechat
import wee_slack
wee_slack.w = FakeWeechat()
from wee_slack import PluginConfig
pc = PluginConfig()
pc.get_debug_level('debug_level')
pc.debug_level

import weechat

from slack.config import SlackWorkspace
from slack.shared import shared


async def init():
    print(shared.workspaces)
    if "wee-slack-test" not in shared.workspaces:
        shared.workspaces["wee-slack-test"] = SlackWorkspace("wee-slack-test")
        shared.workspaces[
            "wee-slack-test"
        ].config.api_token.value = weechat.config_get_plugin("api_token")
        shared.workspaces[
            "wee-slack-test"
        ].config.api_cookies.value = weechat.config_get_plugin("api_cookie")
    workspace = shared.workspaces["wee-slack-test"]
    print(workspace)
    print(workspace.config.slack_timeout.value)
    print(shared.config.color.reaction_suffix.value)

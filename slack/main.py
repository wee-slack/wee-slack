import weechat

from slack import globals as G
from slack.config import SlackWorkspace


async def init():
    print(G.workspaces)
    if "wee-slack-test" not in G.workspaces:
        G.workspaces["wee-slack-test"] = SlackWorkspace("wee-slack-test")
        G.workspaces[
            "wee-slack-test"
        ].config.api_token.value = weechat.config_get_plugin("api_token")
        G.workspaces[
            "wee-slack-test"
        ].config.api_cookies.value = weechat.config_get_plugin("api_cookie")
    workspace = G.workspaces["wee-slack-test"]
    print(workspace)
    print(workspace.config.slack_timeout.value)
    print(G.config.color.reaction_suffix.value)

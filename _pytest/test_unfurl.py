import wee_slack
import pytest
import json

slack = wee_slack

unfurl_map = [
    { "input": "foo",
      "output": "foo",
    },
    { "input": "<@U2147483697|@othernick>: foo",
      "output": "@testuser: foo",
      "ignore_alt_text": True
    },
    { "input": "foo <#C2147483705|#otherchannel> foo",
      "output": "foo #otherchannel foo",
    },
    { "input": "foo <#C2147483705> foo",
      "output": "foo #testchan foo",
    },
    { "input": "url: <https://example.com|example> suffix",
      "output": "url: https://example.com (example) suffix",
    },
    { "input": "url: <https://example.com|example with spaces> suffix",
      "output": "url: https://example.com (example with spaces) suffix",
    },
    { "input": "<@U2147483697|@othernick> multiple unfurl <https://example.com|example with spaces>",
      "output": "@othernick multiple unfurl https://example.com (example with spaces)",
    },
    ]


def test_unfurl_refs(myservers, mychannels, myusers):
    slack.servers = myservers
    slack.channels = mychannels
    slack.users = myusers
    slack.message_cache = {}
    slack.servers[0].users = myusers
    print mychannels[0].identifier

    for k in unfurl_map:
        if "ignore_alt_text" in k:
            assert slack.unfurl_refs(k["input"], ignore_alt_text=k["ignore_alt_text"]) == k["output"]
        else:
            assert slack.unfurl_refs(k["input"]) == k["output"]

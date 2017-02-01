import wee_slack
import pytest

slack = wee_slack


@pytest.mark.parametrize('case', (
    {
        'input': "foo",
        'output': "foo",
    },
    {
        'input': "<@U2147483697|@othernick>: foo",
        'output': "@testuser: foo",
        'ignore_alt_text': True,
    },
    {
        'input': "foo <#C2147483705|#otherchannel> foo",
        'output': "foo #otherchannel foo",
    },
    {
        'input': "foo <#C2147483705> foo",
        'output': "foo #test-chan foo",
    },
    {
        'input': "url: <https://example.com|example> suffix",
        'output': "url: https://example.com (example) suffix",
    },
    {
        'input': "url: <https://example.com|example with spaces> suffix",
        'output': "url: https://example.com (example with spaces) suffix",
    },
    {
        'input': "<@U2147483697|@othernick> multiple unfurl <https://example.com|example with spaces>",
        'output': "@othernick multiple unfurl https://example.com (example with spaces)",
    },
    {
        'input': "try the #test-chan channel",
        'output': "try the #test-chan channel",
    },
))
def test_unfurl_refs(case):
    pass
    #print myslack
    #slack.servers = myslack.server
    #slack.channels = myslack.channel
    #slack.users = myslack.user
    #slack.message_cache = {}
    #slack.servers[0].users = myslack.user
    #print myslack.channel[0].identifier

    #assert slack.unfurl_refs(case['input'], ignore_alt_text=case.get('ignore_alt_text', False)) == case['output']


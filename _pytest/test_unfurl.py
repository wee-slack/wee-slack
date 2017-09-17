import wee_slack
import pytest

slack = wee_slack


@pytest.mark.parametrize('case', (
    {
        'input': "foo",
        'output': "foo",
    },
    {
        'input': "<@U407ABLLW|@othernick>: foo",
        'output': "@alice: foo",
        'ignore_alt_text': True,
    },
    {
        'input': "foo <#C407ABS94|otherchannel> foo",
        'output': "foo #otherchannel foo",
    },
    {
        'input': "foo <#C407ABS94> foo",
        'output': "foo #general foo",
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
        'input': "<@U407ABLLW|@othernick> multiple unfurl <https://example.com|example with spaces>",
        'output': "@othernick multiple unfurl https://example.com (example with spaces)",
    },
    {
        'input': "try the #general channel",
        'output': "try the #general channel",
    },
    {
        'input': "<@U407ABLLW> I think 3 > 2",
        'output': "@alice I think 3 > 2",
    },
))
def test_unfurl_refs(case, realish_eventrouter):
    slack.EVENTROUTER = realish_eventrouter

    result = slack.unfurl_refs(
        case['input'], ignore_alt_text=case.get('ignore_alt_text', False))
    assert result == case['output']

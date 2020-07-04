from __future__ import print_function, unicode_literals

from datetime import datetime, timedelta
import pytest
import time
import wee_slack
import os

os.environ['TZ'] = 'UTC'

@pytest.mark.parametrize('case', (
    {
        'input': "foo",
        'output': "foo",
    },
    {
        'input': "<!channel>",
        'output': "@channel",
    },
    {
        'input': "<!everyone>",
        'output': "@everyone",
    },
    {
        'input': "<!group>",
        'output': "@group",
    },
    {
        'input': "<!here>",
        'output': "@here",
    },
    {
        'input': "<@U407ABLLW|@othernick>: foo",
        'output': "@alice: foo",
    },
    {
        'input': "<@UNKNOWN|@othernick>: foo",
        'output': "@othernick: foo",
    },
    {
        'input': "foo <#C407ABS94|otherchannel> foo",
        'output': "foo #general foo",
    },
    {
        'input': "foo <#UNKNOWN|otherchannel> foo",
        'output': "foo #otherchannel foo",
    },
    {
        'input': "url: <https://example.com|fallback> suffix",
        'output': "url: https://example.com suffix",
        'ignore_alt_text': True,
    },
    {
        'input': "url: <https://example.com|example> suffix",
        'output': "url: https://example.com (example) suffix",
        'auto_link_display': 'both',
    },
    {
        'input': "url: <https://example.com|example with spaces> suffix",
        'output': "url: https://example.com (example with spaces) suffix",
        'auto_link_display': 'both',
    },
    {
        'input': "url: <https://example.com|example.com> suffix",
        'output': "url: https://example.com (example.com) suffix",
        'auto_link_display': 'both',
    },
    {
        'input': "url: <mailto:name@example.com|name@example.com> suffix",
        'output': "url: mailto:name@example.com (name@example.com) suffix",
        'auto_link_display': 'both',
    },
    {
        'input': "url: <https://example.com|example.com> suffix",
        'output': "url: example.com suffix",
        'auto_link_display': 'text',
    },
    {
        'input': "url: <https://example.com|different text> suffix",
        'output': "url: https://example.com (different text) suffix",
        'auto_link_display': 'text',
    },
    {
        'input': "url: <mailto:name@example.com|name@example.com> suffix",
        'output': "url: name@example.com suffix",
        'auto_link_display': 'text',
    },
    {
        'input': "url: <https://example.com|different text> suffix",
        'output': "url: https://example.com (different text) suffix",
        'auto_link_display': 'url',
    },
    {
        'input': "url: <https://example.com|example.com> suffix",
        'output': "url: https://example.com suffix",
        'auto_link_display': 'url',
    },
    {
        'input': "url: <mailto:name@example.com|name@example.com> suffix",
        'output': "url: mailto:name@example.com suffix",
        'auto_link_display': 'url',
    },
    {
        'input': "<@U407ABLLW> multiple unfurl <https://example.com|example with spaces>",
        'output': "@alice multiple unfurl https://example.com (example with spaces)",
        'auto_link_display': 'both',
    },
    {
        'input': "url with equal fallback: <https://example.com|https://example.com> suffix",
        'output': "url with equal fallback: https://example.com suffix",
        'auto_link_display': 'both',
    },
    {
        'input': "try the #general channel",
        'output': "try the #general channel",
    },
    {
        'input': "<@U407ABLLW> I think 3 > 2",
        'output': "@alice I think 3 > 2",
    },
    {
        'input': "<!subteam^TGX0ALBK3|@othersubteam> This is announcement for the dev team",
        'output': "@test This is announcement for the dev team"
    },
    {
        'input': "<!subteam^UNKNOWN|@othersubteam> This is announcement for the dev team",
        'output': "@othersubteam This is announcement for the dev team"
    },
    {
        'input': "Ends <!date^1577880000^{date_num} - {date} - {date_short} - {date_long}|Jan 01, 2020>.",
        'output': "Ends 2020-01-01 - January 01, 2020 - Jan 01, 2020 - Wednesday, January 01, 2020."
    },
    {
        'input': "Ends <!date^1577880000^{time} - {time_secs}|12:00 PM>.",
        'output': "Ends 12:00 - 12:00:00."
    },
    {
        'input': "Ends <!date^1577880000^{date_num} {invalid_token}>.",
        'output': "Ends 2020-01-01 {invalid_token}."
    },
    {
        'input': "Ends <!date^1577880000^{date_num}^http://github.com>.",
        'output': "Ends 2020-01-01 (http://github.com)."
    },
    {
        'input': "Ends <!date^{}^{{date_pretty}} - {{date_short_pretty}} - {{date_long_pretty}}>.".format(
            int(time.mktime(datetime.today().timetuple()))),
        'output': "Ends today - today - today."
    },
    {
        'input': "Ends <!date^{}^{{date_pretty}} - {{date_short_pretty}} - {{date_long_pretty}}>.".format(
            int(time.mktime((datetime.today() - timedelta(days=1)).timetuple()))),
        'output': "Ends yesterday - yesterday - yesterday."
    },
    {
        'input': "Ends <!date^{}^{{date_pretty}} - {{date_short_pretty}} - {{date_long_pretty}}>.".format(
            int(time.mktime((datetime.today() + timedelta(days=1)).timetuple()))),
        'output': "Ends tomorrow - tomorrow - tomorrow."
    },
    {
        'input': "Ends <!date^1577880000^{date_pretty} - {date_short_pretty} - {date_long_pretty}>.",
        'output': "Ends January 01, 2020 - Jan 01, 2020 - Wednesday, January 01, 2020."
    }
))
def test_unfurl_refs(case, realish_eventrouter):
    wee_slack.EVENTROUTER = realish_eventrouter
    wee_slack.config.unfurl_ignore_alt_text = case.get('ignore_alt_text')
    wee_slack.config.unfurl_auto_link_display = case.get('auto_link_display')

    result = wee_slack.unfurl_refs(case['input'])
    assert result == case['output']

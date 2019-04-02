# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals

import re

from wee_slack import linkify_text


def test_linkifytext_does_partial_html_entity_encoding(team):
    text = linkify_text('& < > \' "', team)

    assert text == '&amp; &lt; &gt; \' "'

def test_linkifytext_names_with_paranthesis(team):
    text = linkify_text('@JohnDoe(jdoe): my test message', team)

    assert text == '@JohnDoe(jdoe): my test message'

def test_linkifytext_names_with_accents(team):
    text = linkify_text('@ÁrvíztűrőTükörfúrógép(atukorfurogep): my test message', team)

    assert text == '@ÁrvíztűrőTükörfúrógép(atukorfurogep): my test message'

def test_linkifytext_formatting_characters(team):
    text = linkify_text('\x02\x1Dmy test message\x1D\x02', team)

    assert text == '*_my test message_*'

def test_linkifytext_with_many_paranthesis(team):
    text = linkify_text('@k(o(v)a)())s: my(( test) message', team)

    assert text == '@k(o(v)a)())s: my(( test) message'

def test_linkifytext_names_with_apostrophe(team):
    text = linkify_text('@O\'Connor: my test message', team)

    assert text == '@O\'Connor: my test message'

def test_linkifytext_names_with_subgroup_notification(team):
    subteam = team.subteams['TGX0ALBK3']
    message = 'This is a message for a subteam'
    text = linkify_text('@{}: {}'.format(subteam.handle, message), team)

    assert text == '<!subteam^{}|@{}>: {}'.format(subteam.identifier, subteam.handle, message)

def test_linkifytext_at_channel(team):
    text = linkify_text('@channel: my test message', team)

    assert text == '<!channel>: my test message'

def test_linkifytext_channel(team, channel_general):
    channel_name = re.sub(r'^[#&]', '', channel_general.name)
    text = linkify_text('#{}: my test message'.format(channel_name), team)

    assert text == '<#{}|{}>: my test message'.format(channel_general.id, channel_name)

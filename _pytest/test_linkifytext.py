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
    text = linkify_text('{}: {}'.format(subteam.handle, message), team)

    assert text == '<!subteam^{}|{}>: {}'.format(subteam.identifier, subteam.handle, message)

def test_linkifytext_at_channel(team):
    text = linkify_text('@channel: my test message', team)

    assert text == '<!channel>: my test message'

def test_linkifytext_at_everyone(team):
    text = linkify_text('@everyone: my test message', team)

    assert text == '<!everyone>: my test message'

def test_linkifytext_at_group(team):
    text = linkify_text('@group: my test message', team)

    assert text == '<!group>: my test message'

def test_linkifytext_at_here(team):
    text = linkify_text('@here: my test message', team)

    assert text == '<!here>: my test message'

def test_linkifytext_channel(team, channel_general):
    channel_name = re.sub(r'^[#&]', '', channel_general.name)
    text = linkify_text('#{}: my test message'.format(channel_name), team)

    assert text == '<#{}|{}>: my test message'.format(channel_general.id, channel_name)

def test_linkifytext_not_private_using_hash(team, channel_private):
    channel_name = re.sub(r'^[#&]', '', channel_private.name)
    text = linkify_text('#{}: my test message'.format(channel_name), team)

    assert text == '#{}: my test message'.format(channel_name)

def test_linkifytext_not_private_using_ampersand(team, channel_private):
    channel_name = re.sub(r'^[#&]', '', channel_private.name)
    text = linkify_text('&{}: my test message'.format(channel_name), team)

    assert text == '&amp;{}: my test message'.format(channel_name)

def test_linkifytext_not_dm(team, channel_dm):
    text = linkify_text('#{}: my test message'.format(channel_dm.name), team)

    assert text == '#{}: my test message'.format(channel_dm.name)

def test_linkifytext_not_mpdm(team, channel_mpdm):
    text = linkify_text('#{}: my test message'.format(channel_mpdm.name), team)

    assert text == '#{}: my test message'.format(channel_mpdm.name)

# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from wee_slack import linkify_text


#def test_linkifytext():
#    linkify_text('@ryan')

#    assert False


def test_linkifytext_does_partial_html_entity_encoding(realish_eventrouter):
    team = realish_eventrouter.teams.values()[0]
    channel = team.channels.values()[0]

    text = linkify_text('& < > \' "', team, channel)

    assert text == '&amp; &lt; &gt; \' "'

def test_linkifytext_names_with_paranthesis(realish_eventrouter):
    team = realish_eventrouter.teams.values()[0]
    channel = team.channels.values()[0]

    text = linkify_text('@JohnDoe(jdoe): my test message', team, channel)

    assert text == '@JohnDoe(jdoe): my test message'

def test_linkifytext_names_with_accents(realish_eventrouter):
    team = realish_eventrouter.teams.values()[0]
    channel = team.channels.values()[0]

    text = linkify_text('@ÁrvíztűrőTükörfúrógép(atukorfurogep): my test message', team, channel)

    assert text == '@ÁrvíztűrőTükörfúrógép(atukorfurogep): my test message'

def test_linkifytext_formatting_characters(realish_eventrouter):
    team = realish_eventrouter.teams.values()[0]
    channel = team.channels.values()[0]

    text = linkify_text('\x02\x1Dmy test message\x1D\x02', team, channel)

    assert text == '*_my test message_*'

def test_linkifytext_with_many_paranthesis(realish_eventrouter):
    team = realish_eventrouter.teams.values()[0]
    channel = team.channels.values()[0]

    text = linkify_text('@k(o(v)a)())s: my(( test) message', team, channel)

    assert text == '@k(o(v)a)())s: my(( test) message'

def test_linkifytext_names_with_apostrophe(realish_eventrouter):
    team = realish_eventrouter.teams.values()[0]
    channel = team.channels.values()[0]

    text = linkify_text('@O\'Connor: my test message', team, channel)

    assert text == '@O\'Connor: my test message'

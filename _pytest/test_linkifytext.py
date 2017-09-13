from wee_slack import linkify_text

#def test_linkifytext():
#    linkify_text('@ryan')

#    assert False


def test_linkifytext_does_partial_html_entity_encoding(mock_weechat, realish_eventrouter):
    team = realish_eventrouter.teams.values()[0]
    channel = team.channels.values()[0]

    text = linkify_text('& < > \' "', team, channel)

    assert text == '&amp; &lt; &gt; \' "'

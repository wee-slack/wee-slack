from wee_slack import SlackTS


def test_slackts():
    a = SlackTS("1234.0")
    print a
    b = SlackTS("1234.002")
    print b
    print type(a.major)
    print type(a.minor)
    print type(b.major)
    print type(b.minor)
    print a.minor
    assert a < b
    c = SlackTS()
    assert c > b

    print str(SlackTS())
    #assert False

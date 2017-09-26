from wee_slack import parse_topic_command


def test_parse_topic_without_arguments():
    channel_name, topic = parse_topic_command('/topic')

    assert channel_name is None
    assert topic is None


def test_parse_topic_with_text():
    channel_name, topic = parse_topic_command('/topic some topic text')

    assert channel_name is None
    assert topic == 'some topic text'


def test_parse_topic_with_delete():
    channel_name, topic = parse_topic_command('/topic -delete')

    assert channel_name is None
    assert topic == ''


def test_parse_topic_with_channel():
    channel_name, topic = parse_topic_command('/topic #general')

    assert channel_name == 'general'
    assert topic is None


def test_parse_topic_with_channel_and_text():
    channel_name, topic = parse_topic_command(
        '/topic #general some topic text')

    assert channel_name == 'general'
    assert topic == 'some topic text'


def test_parse_topic_with_channel_and_delete():
    channel_name, topic = parse_topic_command('/topic #general -delete')

    assert channel_name == 'general'
    assert topic == ''

# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals

from wee_slack import url_encode_if_not_encoded


def test_should_url_encode_if_not_encoded():
    value = "="
    encoded = url_encode_if_not_encoded(value)
    assert encoded == "%3D"


def test_should_not_url_encode_if_encoded():
    value = "%3D"
    encoded = url_encode_if_not_encoded(value)
    assert encoded == value

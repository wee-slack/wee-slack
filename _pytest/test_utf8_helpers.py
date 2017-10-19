# -*- coding: utf-8 -*-

from collections import OrderedDict
from wee_slack import decode_from_utf8, encode_to_utf8, utf8_decode


def test_decode_preserves_string_without_utf8():
    assert u'test' == decode_from_utf8(b'test')

def test_decode_preserves_unicode_strings():
    assert u'æøå' == decode_from_utf8(u'æøå')

def test_decode_preserves_mapping_type():
    value_dict = {'a': 'x', 'b': 'y', 'c': 'z'}
    value_ord_dict = OrderedDict(value_dict)
    assert type(value_dict) == type(decode_from_utf8(value_dict))
    assert type(value_ord_dict) == type(decode_from_utf8(value_ord_dict))

def test_decode_preserves_iterable_type():
    value_set = {'a', 'b', 'c'}
    value_tuple = ('a', 'b', 'c')
    assert type(value_set) == type(decode_from_utf8(value_set))
    assert type(value_tuple) == type(decode_from_utf8(value_tuple))

def test_decodes_utf8_string_to_unicode():
    assert u'æøå' == decode_from_utf8(b'æøå')

def test_decodes_utf8_dict_to_unicode():
    assert {u'æ': u'å', u'ø': u'å'} == decode_from_utf8({b'æ': b'å', b'ø': b'å'})

def test_decodes_utf8_list_to_unicode():
    assert [u'æ', u'ø', u'å'] == decode_from_utf8([b'æ', b'ø', b'å'])

def test_encode_preserves_string_without_utf8():
    assert b'test' == encode_to_utf8(u'test')

def test_encode_preserves_byte_strings():
    assert b'æøå' == encode_to_utf8(b'æøå')

def test_encode_preserves_mapping_type():
    value_dict = {'a': 'x', 'b': 'y', 'c': 'z'}
    value_ord_dict = OrderedDict(value_dict)
    assert type(value_dict) == type(encode_to_utf8(value_dict))
    assert type(value_ord_dict) == type(encode_to_utf8(value_ord_dict))

def test_encode_preserves_iterable_type():
    value_set = {'a', 'b', 'c'}
    value_tuple = ('a', 'b', 'c')
    assert type(value_set) == type(encode_to_utf8(value_set))
    assert type(value_tuple) == type(encode_to_utf8(value_tuple))

def test_encodes_utf8_string_to_unicode():
    assert b'æøå' == encode_to_utf8(u'æøå')

def test_encodes_utf8_dict_to_unicode():
    assert {b'æ': b'å', b'ø': b'å'} == encode_to_utf8({u'æ': u'å', u'ø': u'å'})

def test_encodes_utf8_list_to_unicode():
    assert [b'æ', b'ø', b'å'] == encode_to_utf8([u'æ', u'ø', u'å'])

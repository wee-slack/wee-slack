# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals

import sys
from collections import OrderedDict
from wee_slack import decode_from_utf8, encode_to_utf8, utf8_decode


b_ae = 'æ'.encode('utf-8')
b_oe = 'ø'.encode('utf-8')
b_aa = 'å'.encode('utf-8')
b_word = b_ae + b_oe + b_aa


if sys.version_info.major > 2:
    def test_decode_should_not_transform_str():
        assert 'æøå' == decode_from_utf8('æøå')

    def test_decode_should_not_transform_bytes():
        assert b_word == decode_from_utf8(b_word)

    def test_encode_should_not_transform_str():
        assert 'æøå' == encode_to_utf8('æøå')

    def test_encode_should_not_transform_bytes():
        assert b_word == encode_to_utf8(b_word)

else:
    def test_decode_preserves_string_without_utf8():
        assert 'test' == decode_from_utf8(b'test')

    def test_decode_preserves_unicode_strings():
        assert 'æøå' == decode_from_utf8('æøå')

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
        assert 'æøå' == decode_from_utf8(b_word)

    def test_decodes_utf8_dict_to_unicode():
        assert {'æ': 'å', 'ø': 'å'} == decode_from_utf8({b_ae: b_aa, b_oe: b_aa})

    def test_decodes_utf8_list_to_unicode():
        assert ['æ', 'ø', 'å'] == decode_from_utf8([b_ae, b_oe, b_aa])

    def test_encode_preserves_string_without_utf8():
        assert b'test' == encode_to_utf8('test')

    def test_encode_preserves_byte_strings():
        assert b_word == encode_to_utf8(b_word)

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
        assert b_word == encode_to_utf8('æøå')

    def test_encodes_utf8_dict_to_unicode():
        assert {b_ae: b_aa, b_oe: b_aa} == encode_to_utf8({'æ': 'å', 'ø': 'å'})

    def test_encodes_utf8_list_to_unicode():
        assert [b_ae, b_oe, b_aa] == encode_to_utf8(['æ', 'ø', 'å'])

    @utf8_decode
    def method_with_utf8_decode(*args, **kwargs):
        return (args, kwargs)

    def test_utf8_decode():
        args = (b_ae, b_oe, b_aa)
        kwargs = {b_ae: b_aa, b_oe: b_aa}

        result_args, result_kwargs = method_with_utf8_decode(*args, **kwargs)

        assert result_args == decode_from_utf8(args)
        assert result_kwargs == decode_from_utf8(kwargs)

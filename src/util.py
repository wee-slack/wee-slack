"""Assorted utility functions."""

import collections

def encode_to_utf8(data):
    if isinstance(data, unicode):
        return data.encode('utf-8')
    if isinstance(data, bytes):
        return data
    elif isinstance(data, collections.Mapping):
        return type(data)(map(encode_to_utf8, data.iteritems()))
    elif isinstance(data, collections.Iterable):
        return type(data)(map(encode_to_utf8, data))
    else:
        return data


def decode_from_utf8(data):
    if isinstance(data, bytes):
        return data.decode('utf-8')
    if isinstance(data, unicode):
        return data
    elif isinstance(data, collections.Mapping):
        return type(data)(map(decode_from_utf8, data.iteritems()))
    elif isinstance(data, collections.Iterable):
        return type(data)(map(decode_from_utf8, data))
    else:
        return data



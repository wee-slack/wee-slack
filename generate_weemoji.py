#!/usr/bin/python

import json
import sys

all_emojis = json.loads(sys.stdin.read())

def convert_unicode_string(emoji_dict):
    for k, v in emoji_dict.items():
        if k == 'unicode':
            emoji_dict[k] = ''.join([chr(int(x, 16)) for x in v.split('-')])
        if type(v) == dict:
            convert_unicode_string(v)

convert_unicode_string(all_emojis)

with open('weemoji.json', 'w') as weemoji:
    json.dump(all_emojis, weemoji, indent=2, sort_keys=True)
    weemoji.write('\n')

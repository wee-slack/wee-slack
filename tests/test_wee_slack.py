#!/usr/bin/python



import unittest

import sys
sys.dont_write_bytecode = True
import os
sys.path.append(os.path.join('..', '.'))

from wee_slack import *

from mock import MagicMock
from mock import Mock

class FooTest(unittest.TestCase):
    def setUp(self):
        global w
        w = MagicMock()
        #w.color =
        w.color.return_value = 3

        self.something = {}
        self.something2 = {}
        self.something['items'] = SearchList(['a','b','c'])
        self.something2['items'] = SearchList(['a','d','e'])
        self.my_list = SearchList([self.something, self.something2])
        self.meta_list = Meta('items', self.my_list)

    def test_searchlist_find_one_element(self):
        self.assertEqual(self.meta_list.find('a'), 'a')

    def test_searchlist_find_duplicate_elements(self):
        self.something['items'].append('a')
        self.assertEqual(self.meta_list.find('a'), 'a')

    def test_metasearchlist_findfirst_duplicate_elements(self):
        self.assertEqual(w.color('1234','1234'), 3)
        pass
#        print str(self.meta_list)
#        self.assertEqual(self.meta_list.find_first('a'), 'a')

if __name__ == "__main__":
    unittest.main()



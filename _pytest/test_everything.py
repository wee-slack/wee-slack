from __future__ import print_function, unicode_literals

import glob
import json


def test_everything(realish_eventrouter, team):
    datafiles = glob.glob("_pytest/data/websocket/*.json")

    for fname in sorted(datafiles):
        data = json.loads(open(fname, 'r').read())
        team.ws.add(data)
        realish_eventrouter.receive_ws_callback(team.team_hash, None)
        realish_eventrouter.handle_next()

    assert len(realish_eventrouter.queue) == 14

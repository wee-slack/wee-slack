from __future__ import print_function, unicode_literals

import glob
import json

def test_process_subteam_created(mock_websocket, realish_eventrouter):

    eventrouter = realish_eventrouter

    t = eventrouter.teams.keys()[0]

    assert len(eventrouter.teams[t].subteams) == 1

    socket = mock_websocket
    eventrouter.teams[t].ws = socket
    datafiles = glob.glob("_pytest/data/websocket/1483975206.59-subteam_created.json")

    for fname in datafiles:
        data = json.loads(open(fname, 'r').read())
        socket.add(data)
        eventrouter.receive_ws_callback(t)
        eventrouter.handle_next()

    assert len(eventrouter.teams[t].subteams) == 2

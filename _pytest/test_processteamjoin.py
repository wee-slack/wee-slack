import glob
import json

def test_process_team_join(mock_websocket, realish_eventrouter):

    eventrouter = realish_eventrouter

    t = eventrouter.teams.keys()[0]

    #delete charles so we can add him
    del eventrouter.teams[t].users['U4096CBHC']

    assert len(eventrouter.teams[t].users) == 3

    socket = mock_websocket
    eventrouter.teams[t].ws = socket

    datafiles = glob.glob("_pytest/data/websocket/1485975606.59-team_join.json")

    for fname in datafiles:
        data = json.loads(open(fname, 'r').read())
        socket.add(data)
        eventrouter.receive_ws_callback(t)
        eventrouter.handle_next()

    assert len(eventrouter.teams[t].users) == 4

import glob
import json

def test_everything(realish_eventrouter, mock_websocket):

    eventrouter = realish_eventrouter

    t = eventrouter.teams.keys()[0]

    socket = mock_websocket
    eventrouter.teams[t].ws = socket

    datafiles = glob.glob("_pytest/data/websocket/*.json")

    for fname in sorted(datafiles):
        data = json.loads(open(fname, 'r').read())
        socket.add(data)
        eventrouter.receive_ws_callback(t)
        eventrouter.handle_next()

    assert len(eventrouter.queue) == 14

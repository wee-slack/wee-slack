import glob
import json

from wee_slack import ProcessNotImplemented

def test_process_team_join(mock_websocket, realish_eventrouter):

    eventrouter = realish_eventrouter

    t = eventrouter.teams.keys()[0]
    #u = eventrouter.teams[t].users.keys()[0]

    #user = eventrouter.teams[t].users[u]
    #print user

    #delete charles so we can add him
    del eventrouter.teams[t].users['U4096CBHC']

    assert len(eventrouter.teams[t].users) == 3

    socket = mock_websocket
    eventrouter.teams[t].ws = socket

    datafiles = glob.glob("_pytest/data/websocket/1485975606.59-team_join.json")

    print datafiles
    #assert False

    notimplemented = set()

    for fname in datafiles:
        try:
            print "####################"
            data = json.loads(open(fname, 'r').read())
            socket.add(data)
            print data
            eventrouter.receive_ws_callback(t)
            eventrouter.handle_next()
        except ProcessNotImplemented as e:
            notimplemented.add(str(e))
        #this handles some message data not existing - need to fix
        except KeyError:
            pass

    if len(notimplemented) > 0:
        print "####################"
        print sorted(notimplemented)
        print "####################"

    #print len(eventrouter.queue)
    assert len(eventrouter.teams[t].users) == 4




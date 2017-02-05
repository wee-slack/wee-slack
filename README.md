[![Build Status](https://travis-ci.org/wee-slack/wee-ng.svg?branch=master)](https://travis-ci.org/wee-slack/wee-ng)


### Using threads in wee-ng beta (note: you can't start threads yet, but you can participate in existing ones):

1) look for [Threaded: 12345677.0000] at the end of a message. this means it has threads.
2) in the buffer with the threaded message type `/thread 12345677.0000`
3) a new buffer will open named ` +12345677.0000`, which is the thread buffer
4) if you'd like to give thread buffers a friendly name, switch to them and type `/label [newname]`

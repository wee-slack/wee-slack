# Usage:
# 	Building
# 		docker build -t wee-slack .
#	Running (no saved state)
# 		docker run -it \
#			-v /etc/localtime:/etc/localtime:ro \ # for your time
# 			wee-slack
# 	Running (saved state)
# 		docker run -it \
#			-v /etc/localtime:/etc/localtime:ro \ # for your time
# 			-v "${HOME}/.weechat:/home/user/.weechat" \
# 			wee-slack
#
FROM alpine:latest

RUN apk add --no-cache \
	ca-certificates \
	python3 \
	py-pip \
	weechat \
	weechat-perl \
	weechat-python

RUN pip install websocket-client

ENV HOME /home/user

COPY wee_slack.py /home/user/.weechat/python/autoload/wee_slack.py

RUN adduser -S user -h $HOME \
	&& chown -R user $HOME

WORKDIR $HOME
USER user

ENTRYPOINT [ "weechat" ]

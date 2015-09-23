FROM gliderlabs/alpine:latest
MAINTAINER George Lewis <schvin@schvin.net>
ENV REFRESHED_AT 2015-09-22

RUN apk --update add \
    build-base \
    cmake \
    curl \
    curl-dev \
    gcc \
    libgcrypt-dev \
    ncurses-dev \
    py-pip \
    python \
    python-dev \
    unzip \
    zlib

RUN pip install --upgrade pip
RUN pip install websocket-client


# XXX drop privs

RUN curl -LO https://github.com/weechat/weechat/archive/master.zip && \
    unzip master.zip && \
    mkdir weechat-master/build && \
    cd weechat-master/build && \
    cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local && \
    make && \
    make install

RUN adduser -S weechat
USER weechat
RUN mkdir -p /home/weechat/.weechat/python/autoload && chown -R weechat /home/weechat
WORKDIR /home/weechat/.weechat/python/autoload
RUN curl -LO https://raw.githubusercontent.com/rawdigits/wee-slack/master/wee_slack.py

ENTRYPOINT weechat

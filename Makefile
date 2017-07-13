# Multi-file makefile for wee-slack.
#
# Weechat doesn't well support multi-file plugins, so this one is split into
# multiple files for development and then stitched together by the makefile to
# generate a single slack.py.
#
# It also provides some useful targets for development/testing:
# test: run pytest
# install: copy to your weechat python plugins directory
# enable: install, then create a symlink in your weechat autoload directory
# disable, uninstall: inverse of enable and install

# Directory to install plugin to when using `make install` and `make enable`.
WEECHAT_HOME=${HOME}/.weechat

#### User-facing targets.

all: slack.py

test:
	python2 -m pytest

install: ${WEECHAT_HOME}/python/slack.py
uninstall: disable
	rm -f "${WEECHAT_HOME}/python/slack.py"

enable: ${WEECHAT_HOME}/python/autoload/slack.py
disable:
	rm -f "${WEECHAT_HOME}/python/autoload/slack.py"

.PHONY: all test install enable disable uninstall

#### Implementation targets.

# Generate the single-file plugin script.
slack.py: build.sh wee_slack.py src/*.py
	<wee_slack.py ./build.sh >slack.py

# Install slack.py into the weechat plugin directory.
${WEECHAT_HOME}/python/slack.py: slack.py
	cp --remove-destination slack.py "${WEECHAT_HOME}/python/"

# Link the installed slack.py into the autoload directory.
${WEECHAT_HOME}/python/autoload/slack.py: ${WEECHAT_HOME}/python/slack.py
	ln -sf "../slack.py" "${WEECHAT_HOME}/python/autoload/slack.py"


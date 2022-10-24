import os
import sys

sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from slack import globals as G  # pylint: disable=wrong-import-position
from slack.main import main  # pylint: disable=wrong-import-position

G.weechat_callbacks = globals()

if __name__ == "__main__":
    main()

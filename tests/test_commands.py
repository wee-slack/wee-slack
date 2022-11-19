# Test parsing options
# Test calling the correct function

from itertools import accumulate

import slack.commands


def test_all_parent_commands_exist():
    for command in slack.commands.commands:
        parents = accumulate(command.split(" "), lambda x, y: f"{x} {y}")
        for parent in parents:
            assert parent in slack.commands.commands

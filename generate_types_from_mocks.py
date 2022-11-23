#!/usr/bin/python

import ast
import json
from typing import Any, Generator, List


def create_ann_assign(name: str, type_name: str) -> ast.AnnAssign:
    return ast.AnnAssign(ast.Name(name), ast.Name(type_name), simple=True)


def create_class(name: str, body: List[ast.stmt]) -> ast.ClassDef:
    return ast.ClassDef(name, [ast.Name("TypedDict")], [], body=body, decorator_list=[])


def generate(names: List[str], body: Any) -> Generator[ast.stmt, None, str]:
    if isinstance(body, dict):
        class_body: List[ast.stmt] = []
        for key, value in body.items():
            if not isinstance(key, str):
                raise Exception("Only string keys are supported")
            type_name = yield from generate(names + [key.capitalize()], value)
            item = create_ann_assign(key, type_name)
            class_body.append(item)
        class_name = "".join(names)
        yield create_class(class_name, class_body)
        return class_name
    elif isinstance(body, list):
        if body:
            first = yield from generate(names, body[0])
            return f"List[{first}]"
        else:
            return "List"
    else:
        if body is None:
            return "None"
        else:
            return type(body).__name__


def ast_equal(first: ast.stmt, second: ast.stmt):
    return ast.unparse(first) == ast.unparse(second)


def generate_from_file(path: str, name: str):
    with open(path) as f:
        j = json.loads(f.read())
        yield from generate([name], j)


types = [
    [ast.ImportFrom("typing", [ast.Name("TypedDict"), ast.Name("Union")])],
    generate_from_file("mock_data/slack_info_channel_group.json", "ChannelGroup"),
    generate_from_file("mock_data/slack_info_channel_private.json", "ChannelPrivate"),
    generate_from_file("mock_data/slack_info_channel_public.json", "ChannelPublic"),
    generate_from_file("mock_data/slack_info_im.json", "Im"),
    generate_from_file("mock_data/slack_info_mpim_channel.json", "MpimChannel"),
    generate_from_file("mock_data/slack_info_mpim_group.json", "MpimGroup"),
]

for x in types:
    for y in x:
        print(ast.unparse(y))
        print()

# print('SlackConversationInfoResponse = Union[]')

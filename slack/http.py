from __future__ import annotations

import os
import resource
from io import StringIO
from typing import Dict, Tuple

import weechat

from slack.error import HttpError
from slack.log import LogLevel, log
from slack.task import FutureProcess, sleep, weechat_task_cb
from slack.util import get_callback_name


def available_file_descriptors():
    num_current_file_descriptors = len(os.listdir("/proc/self/fd/"))
    max_file_descriptors = min(resource.getrlimit(resource.RLIMIT_NOFILE))
    return max_file_descriptors - num_current_file_descriptors


async def hook_process_hashtable(
    command: str, options: Dict[str, str], timeout: int
) -> Tuple[str, int, str, str]:
    future = FutureProcess()
    log(
        LogLevel.DEBUG,
        f"hook_process_hashtable calling ({future.id}): command: {command}",
    )
    while available_file_descriptors() < 10:
        await sleep(100)
    weechat.hook_process_hashtable(
        command, options, timeout, get_callback_name(weechat_task_cb), future.id
    )

    stdout = StringIO()
    stderr = StringIO()
    return_code = -1

    while return_code == -1:
        next_future = FutureProcess(future.id)
        _, return_code, out, err = await next_future
        log(
            LogLevel.TRACE,
            f"hook_process_hashtable intermediary response ({next_future.id}): command: {command}",
        )
        stdout.write(out)
        stderr.write(err)

    out = stdout.getvalue()
    err = stderr.getvalue().strip()
    log(
        LogLevel.DEBUG,
        f"hook_process_hashtable response ({future.id}): command: {command}, "
        f"return_code: {return_code}, response length: {len(out)}"
        + (f", error: {err}" if err else ""),
    )

    return command, return_code, out, err


async def http_request(
    url: str, options: Dict[str, str], timeout: int, max_retries: int = 5
) -> str:
    options["header"] = "1"
    _, return_code, out, err = await hook_process_hashtable(
        f"url:{url}", options, timeout
    )

    if return_code != 0 or err:
        if max_retries > 0:
            log(
                LogLevel.INFO,
                f"HTTP error, retrying (max {max_retries} times): "
                f"return_code: {return_code}, error: {err}, url: {url}",
            )
            await sleep(1000)
            return await http_request(url, options, timeout, max_retries - 1)
        raise HttpError(url, options, return_code, 0, err)

    parts = out.split("\r\n\r\nHTTP/")
    last_header_part, body = parts[-1].split("\r\n\r\n", 1)
    header_lines = last_header_part.split("\r\n")
    http_status = int(header_lines[0].split(" ")[1])

    if http_status == 429:
        for header in header_lines[1:]:
            name, value = header.split(":", 1)
            if name.lower() == "retry-after":
                retry_after = int(value.strip())
                log(
                    LogLevel.INFO,
                    f"HTTP ratelimit, retrying in {retry_after} seconds, url: {url}",
                )
                await sleep(retry_after * 1000)
                return await http_request(url, options, timeout)

    if http_status >= 400:
        raise HttpError(url, options, return_code, http_status, body)

    return body

from __future__ import annotations

import os
import resource
from io import StringIO
from typing import Dict, Tuple

import weechat

from slack.error import HttpError
from slack.log import DebugMessageType, LogLevel, log
from slack.task import FutureProcess, FutureUrl, sleep, weechat_task_cb
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
        DebugMessageType.LOG,
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
            DebugMessageType.LOG,
            f"hook_process_hashtable intermediary response ({next_future.id}): command: {command}",
        )
        stdout.write(out)
        stderr.write(err)

    out = stdout.getvalue()
    err = stderr.getvalue().strip()
    log(
        LogLevel.DEBUG,
        DebugMessageType.LOG,
        f"hook_process_hashtable response ({future.id}): command: {command}, "
        f"return_code: {return_code}, response length: {len(out)}"
        + (f", error: {err}" if err else ""),
    )

    return command, return_code, out, err


async def hook_url(
    url: str, options: Dict[str, str], timeout: int
) -> Tuple[str, Dict[str, str], Dict[str, str]]:
    future = FutureUrl()
    weechat.hook_url(
        url, options, timeout, get_callback_name(weechat_task_cb), future.id
    )
    return await future


async def http_request_process(
    url: str, options: Dict[str, str], timeout: int
) -> Tuple[int, str, str]:
    options["header"] = "1"
    _, return_code, out, err = await hook_process_hashtable(
        f"url:{url}", options, timeout
    )

    if return_code != 0 or err:
        raise HttpError(url, options, return_code, None, err)

    parts = out.split("\r\n\r\nHTTP/")
    headers, body = parts[-1].split("\r\n\r\n", maxsplit=1)
    http_status = int(headers.split(None, maxsplit=2)[1])
    return http_status, headers, body


async def http_request_url(
    url: str, options: Dict[str, str], timeout: int
) -> Tuple[int, str, str]:
    _, _, output = await hook_url(url, options, timeout)

    if "error" in output:
        raise HttpError(url, options, None, None, output["error"])

    if "response_code" not in output:
        raise HttpError(
            url,
            options,
            None,
            None,
            f"Unexpectedly missing response_code, output: {output}",
        )

    http_status = int(output["response_code"])
    header_parts = output["headers"].split("\r\n\r\nHTTP/")
    return http_status, header_parts[-1], output["output"]


async def http_request(
    url: str, options: Dict[str, str], timeout: int, max_retries: int = 5
) -> str:
    log(
        LogLevel.DEBUG,
        DebugMessageType.HTTP_REQUEST,
        f"requesting: {url}, {options.get('postfields')}",
    )
    try:
        if hasattr(weechat, "hook_url"):
            http_status, headers, body = await http_request_url(url, options, timeout)
        else:
            http_status, headers, body = await http_request_process(
                url, options, timeout
            )
        if http_status >= 500:
            raise HttpError(url, options, None, http_status, body)
    except HttpError as e:
        if max_retries > 0:
            log(
                LogLevel.INFO,
                DebugMessageType.LOG,
                f"HTTP error, retrying (max {max_retries} times): "
                f"return_code: {e.return_code}, error: {e.error}, url: {url}",
            )
            await sleep(1000)
            return await http_request(url, options, timeout, max_retries - 1)
        raise

    if http_status == 429:
        header_lines = headers.split("\r\n")
        for header in header_lines[1:]:
            name, value = header.split(":", maxsplit=1)
            if name.lower() == "retry-after":
                retry_after = int(value.strip())
                log(
                    LogLevel.INFO,
                    DebugMessageType.LOG,
                    f"HTTP ratelimit, retrying in {retry_after} seconds, url: {url}",
                )
                await sleep(retry_after * 1000)
                return await http_request(url, options, timeout)

    if http_status >= 400:
        raise HttpError(url, options, None, http_status, body)

    return body

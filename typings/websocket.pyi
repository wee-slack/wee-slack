from socket import socket
from typing import Any

from _typeshed import ReadableBuffer

STATUS_NORMAL = 1000

class ABNF:
    """
    ABNF frame class.
    See http://tools.ietf.org/html/rfc5234
    and http://tools.ietf.org/html/rfc6455#section-5.2
    """

    # operation code values.
    OPCODE_CONT = 0x0
    OPCODE_TEXT = 0x1
    OPCODE_BINARY = 0x2
    OPCODE_CLOSE = 0x8
    OPCODE_PING = 0x9
    OPCODE_PONG = 0xA

    # available operation code value tuple
    OPCODES = (
        OPCODE_CONT,
        OPCODE_TEXT,
        OPCODE_BINARY,
        OPCODE_CLOSE,
        OPCODE_PING,
        OPCODE_PONG,
    )

    # opcode human readable string
    OPCODE_MAP = {
        OPCODE_CONT: "cont",
        OPCODE_TEXT: "text",
        OPCODE_BINARY: "binary",
        OPCODE_CLOSE: "close",
        OPCODE_PING: "ping",
        OPCODE_PONG: "pong",
    }

    # data length threshold.
    LENGTH_7 = 0x7E
    LENGTH_16 = 1 << 16
    LENGTH_63 = 1 << 63

class WebSocketException(Exception): ...
class WebSocketConnectionClosedException(WebSocketException): ...

class WebSocket:
    sock: socket

    def send(self, payload: str, opcode: int = ABNF.OPCODE_TEXT) -> int: ...
    def ping(self, payload: str = ...) -> None: ...
    def recv_data(
        self, control_frame: bool
    ) -> tuple[
        int,
        Any,
    ]: ...
    def close(
        self, status: int = STATUS_NORMAL, reason: bytes = b"", timeout: int = 3
    ) -> None: ...

def create_connection(
    url: str,
    timeout: int | float | None = ...,
    class_: type[Any] = WebSocket,
    header: list[str] | dict[str, str] | None = ...,
    cookie: str | None = ...,
    origin: str | None = ...,
    suppress_origin: bool | None = ...,
    host: str | None = ...,
    proxy_type: str | None = ...,
    http_proxy_host: str | None = ...,
    http_proxy_port: str | int | None = ...,
    http_no_proxy: list[str] | None = ...,
    http_proxy_auth: tuple[str, str] | None = ...,
    http_proxy_timeout: int | float | None = ...,
    enable_multithread: bool | None = ...,
    redirect_limit: int | None = ...,
    sockopt: tuple[int, int, int | ReadableBuffer]
    | tuple[int, int, None, int]
    | None = ...,
    sslopt: dict[str, Any] | None = ...,
    subprotocols: list[str] | None = ...,
    skip_utf8_validation: bool | None = ...,
    socket: socket | None = ...,
) -> WebSocket: ...

from socket import socket
from typing import Any, Dict, Optional, Tuple

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

    def recv_data(
        self, control_frame: bool
    ) -> Tuple[int, Any,]: ...

def create_connection(
    url: str, timeout: Optional[int], **options: Dict[str, Any]
) -> WebSocket: ...

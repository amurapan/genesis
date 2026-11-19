"""Bounded JSON-lines transport. No business rules or private data."""

import json
import os
import selectors
import time

MAX_MESSAGE = 4 * 1024 * 1024


class ProtocolError(Exception):
    pass


def _constant(value):
    raise ProtocolError("Non-finite JSON number")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("Duplicate JSON key")
        result[key] = value
    return result


def loads(value):
    try:
        return json.loads(value, parse_constant=_constant, object_pairs_hook=_pairs)
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise ProtocolError("Invalid JSON") from exc


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


class Wire:
    """Deadlines also cover partial lines and blocked writers."""

    def __init__(self, reader, writer):
        self.reader = reader.fileno()
        self.writer = writer.fileno()
        os.set_blocking(self.reader, False)
        os.set_blocking(self.writer, False)
        self.buffer = bytearray()

    @staticmethod
    def _wait(fd, event, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Protocol deadline")
        with selectors.DefaultSelector() as selector:
            selector.register(fd, event)
            if not selector.select(remaining):
                raise TimeoutError("Protocol deadline")

    def send(self, value, timeout=5.0):
        data = (dumps(value) + "\n").encode()
        if len(data) > MAX_MESSAGE:
            raise ProtocolError("Message too large")
        deadline = time.monotonic() + timeout
        view = memoryview(data)
        while view:
            self._wait(self.writer, selectors.EVENT_WRITE, deadline)
            try:
                written = os.write(self.writer, view)
            except BlockingIOError:
                continue
            view = view[written:]

    def receive(self, timeout=5.0):
        deadline = time.monotonic() + timeout
        while True:
            newline = self.buffer.find(b"\n")
            if newline >= 0:
                if newline > MAX_MESSAGE:
                    raise ProtocolError("Message too large")
                line = bytes(self.buffer[:newline])
                del self.buffer[:newline + 1]
                return loads(line)
            if len(self.buffer) > MAX_MESSAGE:
                raise ProtocolError("Message too large")
            self._wait(self.reader, selectors.EVENT_READ, deadline)
            try:
                chunk = os.read(self.reader, 65536)
            except BlockingIOError:
                continue
            if not chunk:
                raise EOFError("Peer closed")
            self.buffer.extend(chunk)

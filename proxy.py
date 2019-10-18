#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    proxy.py
    ~~~~~~~~
    ⚡⚡⚡ Fast, Lightweight, Programmable Proxy Server in a single Python file.

    :copyright: (c) 2013-present by Abhinav Singh and contributors.
    :license: BSD, see LICENSE for more details.
"""
import argparse
import asyncio
import base64
import contextlib
import errno
import functools
import hashlib
import importlib
import inspect
import io
import ipaddress
import json
import logging
import mimetypes
import multiprocessing
import os
import pathlib
import queue
import secrets
import selectors
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
from abc import ABC, abstractmethod
from multiprocessing import connection
from multiprocessing.reduction import send_handle, recv_handle
from types import TracebackType
from typing import Any, Dict, List, Tuple, Optional, Union, NamedTuple, Callable, Type, TypeVar
from typing import cast, Generator, TYPE_CHECKING
from urllib import parse as urlparse

from typing_extensions import Protocol

if os.name != 'nt':
    import resource

PROXY_PY_DIR = os.path.dirname(os.path.realpath(__file__))
PROXY_PY_START_TIME = time.time()

VERSION = (1, 2, 0)
__version__ = '.'.join(map(str, VERSION[0:3]))
__description__ = '⚡⚡⚡ Fast, Lightweight, Programmable Proxy Server in a single Python file.'
__author__ = 'Abhinav Singh'
__author_email__ = 'mailsforabhinav@gmail.com'
__homepage__ = 'https://github.com/abhinavsingh/proxy.py'
__download_url__ = '%s/archive/master.zip' % __homepage__
__license__ = 'BSD'

# Defaults
DEFAULT_BACKLOG = 100
DEFAULT_BASIC_AUTH = None
DEFAULT_BUFFER_SIZE = 1024 * 1024
DEFAULT_CA_CERT_DIR = None
DEFAULT_CA_CERT_FILE = None
DEFAULT_CA_KEY_FILE = None
DEFAULT_CA_SIGNING_KEY_FILE = None
DEFAULT_CERT_FILE = None
DEFAULT_CLIENT_RECVBUF_SIZE = DEFAULT_BUFFER_SIZE
DEFAULT_DEVTOOLS_WS_PATH = b'/devtools'
DEFAULT_DISABLE_HEADERS: List[bytes] = []
DEFAULT_DISABLE_HTTP_PROXY = False
DEFAULT_ENABLE_DEVTOOLS = False
DEFAULT_ENABLE_STATIC_SERVER = False
DEFAULT_ENABLE_WEB_SERVER = False
DEFAULT_IPV4_HOSTNAME = ipaddress.IPv4Address('127.0.0.1')
DEFAULT_IPV6_HOSTNAME = ipaddress.IPv6Address('::1')
DEFAULT_KEY_FILE = None
DEFAULT_LOG_FILE = None
DEFAULT_LOG_FORMAT = '%(asctime)s - pid:%(process)d [%(levelname)-.1s] %(funcName)s:%(lineno)d - %(message)s'
DEFAULT_LOG_LEVEL = 'INFO'
DEFAULT_NUM_WORKERS = 0
DEFAULT_OPEN_FILE_LIMIT = 1024
DEFAULT_PAC_FILE = None
DEFAULT_PAC_FILE_URL_PATH = b'/'
DEFAULT_PID_FILE = None
DEFAULT_PLUGINS = ''
DEFAULT_PORT = 8899
DEFAULT_SERVER_RECVBUF_SIZE = DEFAULT_BUFFER_SIZE
DEFAULT_STATIC_SERVER_DIR = os.path.join(PROXY_PY_DIR, 'public')
DEFAULT_THREADLESS = False
DEFAULT_TIMEOUT = 10
DEFAULT_VERSION = False
UNDER_TEST = False  # Set to True if under test

logger = logging.getLogger(__name__)


def text_(s: Any, encoding: str = 'utf-8', errors: str = 'strict') -> Any:
    """Utility to ensure text-like usability.

    If s is of type bytes or int, return s.decode(encoding, errors),
    otherwise return s as it is."""
    if isinstance(s, int):
        return str(s)
    if isinstance(s, bytes):
        return s.decode(encoding, errors)
    return s


def bytes_(s: Any, encoding: str = 'utf-8', errors: str = 'strict') -> Any:
    """Utility to ensure binary-like usability.

    If s is type str or int, return s.encode(encoding, errors),
    otherwise return s as it is."""
    if isinstance(s, int):
        s = str(s)
    if isinstance(s, str):
        return s.encode(encoding, errors)
    return s


version = bytes_(__version__)
CRLF, COLON, WHITESPACE, COMMA, DOT, SLASH, HTTP_1_1 = b'\r\n', b':', b' ', b',', b'.', b'/', b'HTTP/1.1'
PROXY_AGENT_HEADER_KEY = b'Proxy-agent'
PROXY_AGENT_HEADER_VALUE = b'proxy.py v' + version
PROXY_AGENT_HEADER = PROXY_AGENT_HEADER_KEY + \
    COLON + WHITESPACE + PROXY_AGENT_HEADER_VALUE

TcpConnectionTypes = NamedTuple('TcpConnectionTypes', [
    ('SERVER', int),
    ('CLIENT', int),
])
tcpConnectionTypes = TcpConnectionTypes(1, 2)

ChunkParserStates = NamedTuple('ChunkParserStates', [
    ('WAITING_FOR_SIZE', int),
    ('WAITING_FOR_DATA', int),
    ('COMPLETE', int),
])
chunkParserStates = ChunkParserStates(1, 2, 3)

HttpStatusCodes = NamedTuple('HttpStatusCodes', [
    # 1xx
    ('CONTINUE', int),
    ('SWITCHING_PROTOCOLS', int),
    # 2xx
    ('OK', int),
    # 3xx
    ('MOVED_PERMANENTLY', int),
    ('SEE_OTHER', int),
    ('TEMPORARY_REDIRECT', int),
    ('PERMANENT_REDIRECT', int),
    # 4xx
    ('BAD_REQUEST', int),
    ('UNAUTHORIZED', int),
    ('FORBIDDEN', int),
    ('NOT_FOUND', int),
    ('PROXY_AUTH_REQUIRED', int),
    ('REQUEST_TIMEOUT', int),
    ('I_AM_A_TEAPOT', int),
    # 5xx
    ('INTERNAL_SERVER_ERROR', int),
    ('NOT_IMPLEMENTED', int),
    ('BAD_GATEWAY', int),
    ('GATEWAY_TIMEOUT', int),
    ('NETWORK_READ_TIMEOUT_ERROR', int),
    ('NETWORK_CONNECT_TIMEOUT_ERROR', int),
])
httpStatusCodes = HttpStatusCodes(
    100, 101,
    200,
    301, 303, 307, 308,
    400, 401, 403, 404, 407, 408, 418,
    500, 501, 502, 504, 598, 599
)

HttpMethods = NamedTuple('HttpMethods', [
    ('GET', bytes),
    ('HEAD', bytes),
    ('POST', bytes),
    ('PUT', bytes),
    ('DELETE', bytes),
    ('CONNECT', bytes),
    ('OPTIONS', bytes),
    ('TRACE', bytes),
    ('PATCH', bytes),
])
httpMethods = HttpMethods(
    b'GET',
    b'HEAD',
    b'POST',
    b'PUT',
    b'DELETE',
    b'CONNECT',
    b'OPTIONS',
    b'TRACE',
    b'PATCH',
)

HttpParserStates = NamedTuple('HttpParserStates', [
    ('INITIALIZED', int),
    ('LINE_RCVD', int),
    ('RCVING_HEADERS', int),
    ('HEADERS_COMPLETE', int),
    ('RCVING_BODY', int),
    ('COMPLETE', int),
])
httpParserStates = HttpParserStates(1, 2, 3, 4, 5, 6)

HttpParserTypes = NamedTuple('HttpParserTypes', [
    ('REQUEST_PARSER', int),
    ('RESPONSE_PARSER', int),
])
httpParserTypes = HttpParserTypes(1, 2)

HttpProtocolTypes = NamedTuple('HttpProtocolTypes', [
    ('HTTP', int),
    ('HTTPS', int),
    ('WEBSOCKET', int),
])
httpProtocolTypes = HttpProtocolTypes(1, 2, 3)

WebsocketOpcodes = NamedTuple('WebsocketOpcodes', [
    ('CONTINUATION_FRAME', int),
    ('TEXT_FRAME', int),
    ('BINARY_FRAME', int),
    ('CONNECTION_CLOSE', int),
    ('PING', int),
    ('PONG', int),
])
websocketOpcodes = WebsocketOpcodes(0x0, 0x1, 0x2, 0x8, 0x9, 0xA)


def build_http_request(method: bytes, url: bytes,
                       protocol_version: bytes = HTTP_1_1,
                       headers: Optional[Dict[bytes, bytes]] = None,
                       body: Optional[bytes] = None) -> bytes:
    """Build and returns a HTTP request packet."""
    if headers is None:
        headers = {}
    return build_http_pkt(
        [method, url, protocol_version], headers, body)


def build_http_response(status_code: int,
                        protocol_version: bytes = HTTP_1_1,
                        reason: Optional[bytes] = None,
                        headers: Optional[Dict[bytes, bytes]] = None,
                        body: Optional[bytes] = None) -> bytes:
    """Build and returns a HTTP response packet."""
    line = [protocol_version, bytes_(status_code)]
    if reason:
        line.append(reason)
    if headers is None:
        headers = {}
    has_content_length = False
    has_transfer_encoding = False
    for k in headers:
        if k.lower() == b'content-length':
            has_content_length = True
        if k.lower() == b'transfer-encoding':
            has_transfer_encoding = True
    if body is not None and \
            not has_transfer_encoding and \
            not has_content_length:
        headers[b'Content-Length'] = bytes_(len(body))
    return build_http_pkt(line, headers, body)


def build_http_header(k: bytes, v: bytes) -> bytes:
    """Build and return a HTTP header line for use in raw packet."""
    return k + COLON + WHITESPACE + v


def build_http_pkt(line: List[bytes],
                   headers: Optional[Dict[bytes, bytes]] = None,
                   body: Optional[bytes] = None) -> bytes:
    """Build and returns a HTTP request or response packet."""
    req = WHITESPACE.join(line) + CRLF
    if headers is not None:
        for k in headers:
            req += build_http_header(k, headers[k]) + CRLF
    req += CRLF
    if body:
        req += body
    return req


def build_websocket_handshake_request(
        key: bytes,
        method: bytes = b'GET',
        url: bytes = b'/') -> bytes:
    """
    Build and returns a Websocket handshake request packet.

    :param key: Sec-WebSocket-Key header value.
    :param method: HTTP method.
    :param url: Websocket request path.
    """
    return build_http_request(
        method, url,
        headers={
            b'Connection': b'upgrade',
            b'Upgrade': b'websocket',
            b'Sec-WebSocket-Key': key,
            b'Sec-WebSocket-Version': b'13',
        }
    )


def build_websocket_handshake_response(accept: bytes) -> bytes:
    """
    Build and returns a Websocket handshake response packet.

    :param accept: Sec-WebSocket-Accept header value
    """
    return build_http_response(
        101, reason=b'Switching Protocols',
        headers={
            b'Upgrade': b'websocket',
            b'Connection': b'Upgrade',
            b'Sec-WebSocket-Accept': accept
        }
    )


def find_http_line(raw: bytes) -> Tuple[Optional[bytes], bytes]:
    """Find and returns first line ending in CRLF along with following buffer.

    If no ending CRLF is found, line is None."""
    pos = raw.find(CRLF)
    if pos == -1:
        return None, raw
    line = raw[:pos]
    rest = raw[pos + len(CRLF):]
    return line, rest


def new_socket_connection(addr: Tuple[str, int]) -> socket.socket:
    conn = None
    try:
        ip = ipaddress.ip_address(addr[0])
        if ip.version == 4:
            conn = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM, 0)
            conn.connect(addr)
        else:
            conn = socket.socket(
                socket.AF_INET6, socket.SOCK_STREAM, 0)
            conn.connect((addr[0], addr[1], 0, 0))
    except ValueError:
        pass    # does not appear to be an IPv4 or IPv6 address

    if conn is not None:
        return conn

    # try to establish dual stack IPv4/IPv6 connection.
    return socket.create_connection(addr)


class socket_connection(contextlib.ContextDecorator):
    """Same as new_socket_connection but as a context manager and decorator."""

    def __init__(self, addr: Tuple[str, int]):
        self.addr: Tuple[str, int] = addr
        self.conn: Optional[socket.socket] = None
        super().__init__()

    def __enter__(self) -> socket.socket:
        self.conn = new_socket_connection(self.addr)
        return self.conn

    def __exit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc_val: Optional[BaseException],
            exc_tb: Optional[TracebackType]) -> bool:
        if self.conn:
            self.conn.close()
        return False

    def __call__(self, func: Callable[..., Any]) -> Callable[[socket.socket], Any]:
        @functools.wraps(func)
        def decorated(*args: Any, **kwargs: Any) -> Any:
            with self as conn:
                return func(conn, *args, **kwargs)
        return decorated


class _HasFileno(Protocol):
    def fileno(self) -> int:
        ...     # pragma: no cover


class TcpConnectionUninitializedException(Exception):
    pass


class TcpConnection(ABC):
    """TCP server/client connection abstraction.

    Main motivation of this class is to provide a buffer management
    when reading and writing into the socket.

    Implement the connection property abstract method to return
    a socket connection object."""

    def __init__(self, tag: int):
        self.buffer: bytes = b''
        self.closed: bool = False
        self.tag: str = 'server' if tag == tcpConnectionTypes.SERVER else 'client'

    @property
    @abstractmethod
    def connection(self) -> Union[ssl.SSLSocket, socket.socket]:
        """Must return the socket connection to use in this class."""
        raise TcpConnectionUninitializedException()     # pragma: no cover

    def send(self, data: bytes) -> int:
        """Users must handle BrokenPipeError exceptions"""
        return self.connection.send(data)

    def recv(self, buffer_size: int = DEFAULT_BUFFER_SIZE) -> Optional[bytes]:
        """Users must handle socket.error exceptions"""
        data: bytes = self.connection.recv(buffer_size)
        if len(data) == 0:
            return None
        logger.debug(
            'received %d bytes from %s' %
            (len(data), self.tag))
        # logger.info(data)
        return data

    def close(self) -> bool:
        if not self.closed:
            self.connection.close()
            self.closed = True
        return self.closed

    def buffer_size(self) -> int:
        return len(self.buffer)

    def has_buffer(self) -> bool:
        return self.buffer_size() > 0

    def queue(self, data: bytes) -> int:
        self.buffer += data
        return len(data)

    def flush(self) -> int:
        """Users must handle BrokenPipeError exceptions"""
        if self.buffer_size() == 0:
            return 0
        sent: int = self.send(self.buffer)
        # logger.info(self.buffer[:sent])
        self.buffer = self.buffer[sent:]
        logger.debug('flushed %d bytes to %s' % (sent, self.tag))
        return sent


class TcpServerConnection(TcpConnection):
    """Establishes connection to upstream server."""

    def __init__(self, host: str, port: int):
        super().__init__(tcpConnectionTypes.SERVER)
        self._conn: Optional[Union[ssl.SSLSocket, socket.socket]] = None
        self.addr: Tuple[str, int] = (host, int(port))

    @property
    def connection(self) -> Union[ssl.SSLSocket, socket.socket]:
        if self._conn is None:
            raise TcpConnectionUninitializedException()
        return self._conn

    def connect(self) -> None:
        if self._conn is not None:
            return
        self._conn = new_socket_connection(self.addr)


class TcpClientConnection(TcpConnection):
    """An accepted client connection request."""

    def __init__(self,
                 conn: Union[ssl.SSLSocket, socket.socket],
                 addr: Tuple[str, int]):
        super().__init__(tcpConnectionTypes.CLIENT)
        self._conn: Optional[Union[ssl.SSLSocket, socket.socket]] = conn
        self.addr: Tuple[str, int] = addr

    @property
    def connection(self) -> Union[ssl.SSLSocket, socket.socket]:
        if self._conn is None:
            raise TcpConnectionUninitializedException()
        return self._conn


class ChunkParser:
    """HTTP chunked encoding response parser."""

    def __init__(self) -> None:
        self.state = chunkParserStates.WAITING_FOR_SIZE
        self.body: bytes = b''  # Parsed chunks
        self.chunk: bytes = b''  # Partial chunk received
        # Expected size of next following chunk
        self.size: Optional[int] = None

    def parse(self, raw: bytes) -> bytes:
        more = True if len(raw) > 0 else False
        while more and self.state != chunkParserStates.COMPLETE:
            more, raw = self.process(raw)
        return raw

    def process(self, raw: bytes) -> Tuple[bool, bytes]:
        if self.state == chunkParserStates.WAITING_FOR_SIZE:
            # Consume prior chunk in buffer
            # in case chunk size without CRLF was received
            raw = self.chunk + raw
            self.chunk = b''
            # Extract following chunk data size
            line, raw = find_http_line(raw)
            # CRLF not received or Blank line was received.
            if line is None or line.strip() == b'':
                self.chunk = raw
                raw = b''
            else:
                self.size = int(line, 16)
                self.state = chunkParserStates.WAITING_FOR_DATA
        elif self.state == chunkParserStates.WAITING_FOR_DATA:
            assert self.size is not None
            remaining = self.size - len(self.chunk)
            self.chunk += raw[:remaining]
            raw = raw[remaining:]
            if len(self.chunk) == self.size:
                raw = raw[len(CRLF):]
                self.body += self.chunk
                if self.size == 0:
                    self.state = chunkParserStates.COMPLETE
                else:
                    self.state = chunkParserStates.WAITING_FOR_SIZE
                self.chunk = b''
                self.size = None
        return len(raw) > 0, raw

    @staticmethod
    def to_chunks(raw: bytes, chunk_size: int = DEFAULT_BUFFER_SIZE) -> bytes:
        chunks: List[bytes] = []
        for i in range(0, len(raw), chunk_size):
            chunk = raw[i: i + chunk_size]
            chunks.append(bytes_('{:x}'.format(len(chunk))))
            chunks.append(chunk)
        chunks.append(bytes_('{:x}'.format(0)))
        chunks.append(b'')
        return CRLF.join(chunks) + CRLF


T = TypeVar('T', bound='HttpParser')


class HttpParser:
    """HTTP request/response parser."""

    def __init__(self, parser_type: int) -> None:
        self.type: int = parser_type
        self.state: int = httpParserStates.INITIALIZED

        # Raw bytes as passed to parse(raw) method and its total size
        self.bytes: bytes = b''
        self.total_size: int = 0

        # Buffer to hold unprocessed bytes
        self.buffer: bytes = b''

        self.headers: Dict[bytes, Tuple[bytes, bytes]] = dict()
        self.body: Optional[bytes] = None

        self.method: Optional[bytes] = None
        self.url: Optional[urlparse.SplitResultBytes] = None
        self.code: Optional[bytes] = None
        self.reason: Optional[bytes] = None
        self.version: Optional[bytes] = None

        self.chunk_parser: Optional[ChunkParser] = None

        # This cleans up developer APIs as Python urlparse.urlsplit behaves differently
        # for incoming proxy request and incoming web request.  Web request is the one
        # which is broken.
        self.host: Optional[bytes] = None
        self.port: Optional[int] = None
        self.path: Optional[bytes] = None

    @classmethod
    def request(cls: Type[T], raw: bytes) -> T:
        parser = cls(httpParserTypes.REQUEST_PARSER)
        parser.parse(raw)
        return parser

    @classmethod
    def response(cls: Type[T], raw: bytes) -> T:
        parser = cls(httpParserTypes.RESPONSE_PARSER)
        parser.parse(raw)
        return parser

    def header(self, key: bytes) -> bytes:
        if key.lower() not in self.headers:
            raise KeyError('%s not found in headers', text_(key))
        return self.headers[key.lower()][1]

    def has_header(self, key: bytes) -> bool:
        return key.lower() in self.headers

    def add_header(self, key: bytes, value: bytes) -> None:
        self.headers[key.lower()] = (key, value)

    def add_headers(self, headers: List[Tuple[bytes, bytes]]) -> None:
        for (key, value) in headers:
            self.add_header(key, value)

    def del_header(self, header: bytes) -> None:
        if header.lower() in self.headers:
            del self.headers[header.lower()]

    def del_headers(self, headers: List[bytes]) -> None:
        for key in headers:
            self.del_header(key.lower())

    def set_url(self, url: bytes) -> None:
        self.url = urlparse.urlsplit(url)
        self.set_line_attributes()

    def set_line_attributes(self) -> None:
        if self.type == httpParserTypes.REQUEST_PARSER:
            if self.method == httpMethods.CONNECT and self.url:
                u = urlparse.urlsplit(b'//' + self.url.path)
                self.host, self.port = u.hostname, u.port
            elif self.url:
                self.host, self.port = self.url.hostname, self.url.port \
                    if self.url.port else 80
            else:
                raise KeyError('Invalid request\n%s' % self.bytes)
            self.path = self.build_url()

    def is_chunked_encoded(self) -> bool:
        return b'transfer-encoding' in self.headers and \
            self.headers[b'transfer-encoding'][1].lower() == b'chunked'

    def parse(self, raw: bytes) -> None:
        """Parses Http request out of raw bytes.

        Check HttpParser state after parse has successfully returned."""
        self.bytes += raw
        self.total_size += len(raw)

        # Prepend past buffer
        raw = self.buffer + raw
        self.buffer = b''

        more = True if len(raw) > 0 else False
        while more and self.state != httpParserStates.COMPLETE:
            if self.state in (
                    httpParserStates.HEADERS_COMPLETE,
                    httpParserStates.RCVING_BODY):
                if b'content-length' in self.headers:
                    self.state = httpParserStates.RCVING_BODY
                    if self.body is None:
                        self.body = b''
                    total_size = int(self.header(b'content-length'))
                    received_size = len(self.body)
                    self.body += raw[:total_size - received_size]
                    if self.body and \
                            len(self.body) == int(self.header(b'content-length')):
                        self.state = httpParserStates.COMPLETE
                    more, raw = len(raw) > 0, raw[total_size - received_size:]
                elif self.is_chunked_encoded():
                    if not self.chunk_parser:
                        self.chunk_parser = ChunkParser()
                    raw = self.chunk_parser.parse(raw)
                    if self.chunk_parser.state == chunkParserStates.COMPLETE:
                        self.body = self.chunk_parser.body
                        self.state = httpParserStates.COMPLETE
                        self.chunk_parser.__init__()
                    more = False
            else:
                more, raw = self.process(raw)
        self.buffer = raw

    def process(self, raw: bytes) -> Tuple[bool, bytes]:
        """Returns False when no CRLF could be found in received bytes."""
        line, raw = find_http_line(raw)
        if line is None:
            return False, raw

        if self.state == httpParserStates.INITIALIZED:
            self.process_line(line)
            self.state = httpParserStates.LINE_RCVD
        elif self.state in (httpParserStates.LINE_RCVD, httpParserStates.RCVING_HEADERS):
            if self.state == httpParserStates.LINE_RCVD:
                # LINE_RCVD state is equivalent to RCVING_HEADERS
                self.state = httpParserStates.RCVING_HEADERS
            if line.strip() == b'':  # Blank line received.
                self.state = httpParserStates.HEADERS_COMPLETE
            else:
                self.process_header(line)

        # When connect request is received without a following host header
        # See
        # `TestHttpParser.test_connect_request_without_host_header_request_parse`
        # for details
        if self.state == httpParserStates.LINE_RCVD and \
                self.type == httpParserTypes.RESPONSE_PARSER and \
                raw == CRLF:
            self.state = httpParserStates.COMPLETE
        # When raw request has ended with \r\n\r\n and no more http headers are expected
        # See `TestHttpParser.test_request_parse_without_content_length` and
        # `TestHttpParser.test_response_parse_without_content_length` for details
        elif self.state == httpParserStates.HEADERS_COMPLETE and \
                self.type == httpParserTypes.REQUEST_PARSER and \
                self.method != httpMethods.POST and \
                self.bytes.endswith(CRLF * 2):
            self.state = httpParserStates.COMPLETE
        elif self.state == httpParserStates.HEADERS_COMPLETE and \
                self.type == httpParserTypes.REQUEST_PARSER and \
                self.method == httpMethods.POST and \
                not self.is_chunked_encoded() and \
                (b'content-length' not in self.headers or
                 (b'content-length' in self.headers and
                  int(self.headers[b'content-length'][1]) == 0)) and \
                self.bytes.endswith(CRLF * 2):
            self.state = httpParserStates.COMPLETE

        return len(raw) > 0, raw

    def process_line(self, raw: bytes) -> None:
        line = raw.split(WHITESPACE)
        if self.type == httpParserTypes.REQUEST_PARSER:
            self.method = line[0].upper()
            self.set_url(line[1])
            self.version = line[2]
        else:
            self.version = line[0]
            self.code = line[1]
            self.reason = WHITESPACE.join(line[2:])

    def process_header(self, raw: bytes) -> None:
        parts = raw.split(COLON)
        key = parts[0].strip()
        value = COLON.join(parts[1:]).strip()
        self.add_headers([(key, value)])

    def build_url(self) -> bytes:
        if not self.url:
            return b'/None'
        url = self.url.path
        if url == b'':
            url = b'/'
        if not self.url.query == b'':
            url += b'?' + self.url.query
        if not self.url.fragment == b'':
            url += b'#' + self.url.fragment
        return url

    def build(self, disable_headers: Optional[List[bytes]] = None) -> bytes:
        assert self.method and self.version and self.path
        if disable_headers is None:
            disable_headers = DEFAULT_DISABLE_HEADERS
        body: Optional[bytes] = ChunkParser.to_chunks(self.body) \
            if self.is_chunked_encoded() and self.body else \
            self.body
        return build_http_request(
            self.method, self.path, self.version,
            headers={} if not self.headers else {self.headers[k][0]: self.headers[k][1] for k in self.headers if
                                                 k.lower() not in disable_headers},
            body=body
        )

    def has_upstream_server(self) -> bool:
        """Host field SHOULD be None for incoming local WebServer requests."""
        return True if self.host is not None else False

    def is_http_1_1_keep_alive(self) -> bool:
        return self.version == HTTP_1_1 and \
            (not self.has_header(b'Connection') or
             self.header(b'Connection').lower() == b'keep-alive')


class AcceptorPool:
    """AcceptorPool.

    Pre-spawns worker processes to utilize all cores available on the system.  Server socket connection is
    dispatched over a pipe to workers.  Each worker accepts incoming client request and spawns a
    separate thread to handle the client request.
    """

    def __init__(self,
                 hostname: Union[ipaddress.IPv4Address,
                                 ipaddress.IPv6Address],
                 port: int, backlog: int, num_workers: int,
                 threadless: bool,
                 work_klass: type,
                 **kwargs: Any) -> None:
        self.threadless = threadless
        self.running: bool = False

        self.hostname: Union[ipaddress.IPv4Address,
                             ipaddress.IPv6Address] = hostname
        self.port: int = port
        self.family: socket.AddressFamily = socket.AF_INET6 if hostname.version == 6 else socket.AF_INET
        self.backlog: int = backlog
        self.socket: Optional[socket.socket] = None

        self.num_acceptors = num_workers
        self.acceptors: List[Acceptor] = []
        self.work_queues: List[connection.Connection] = []

        self.work_klass = work_klass
        self.kwargs = kwargs

    def listen(self) -> None:
        self.socket = socket.socket(self.family, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((str(self.hostname), self.port))
        self.socket.listen(self.backlog)
        self.socket.setblocking(False)
        logger.info('Listening on %s:%d' % (self.hostname, self.port))

    def start_workers(self) -> None:
        """Start worker processes."""
        for _ in range(self.num_acceptors):
            work_queue = multiprocessing.Pipe()
            acceptor = Acceptor(
                self.family,
                self.threadless,
                work_queue[1],
                self.work_klass,
                **self.kwargs
            )
            # acceptor.daemon = True
            acceptor.start()
            self.acceptors.append(acceptor)
            self.work_queues.append(work_queue[0])
        logger.info('Started %d workers' % self.num_acceptors)

    def shutdown(self) -> None:
        logger.info('Shutting down %d workers' % self.num_acceptors)
        for acceptor in self.acceptors:
            acceptor.join()
        for work_queue in self.work_queues:
            work_queue.close()

    def setup(self) -> None:
        """Listen on port, setup workers and pass server socket to workers."""
        self.running = True
        self.listen()
        self.start_workers()

        # Send server socket to all acceptor processes.
        assert self.socket is not None
        for index in range(self.num_acceptors):
            send_handle(
                self.work_queues[index],
                self.socket.fileno(),
                self.acceptors[index].pid
            )
        self.socket.close()


class ThreadlessWork(ABC):
    """Implement ThreadlessWork to hook into the event loop provided by Threadless process."""

    @abstractmethod
    def initialize(self) -> None:
        pass    # pragma: no cover

    @abstractmethod
    def is_inactive(self) -> bool:
        return False    # pragma: no cover

    @abstractmethod
    def get_events(self) -> Dict[socket.socket, int]:
        return {}   # pragma: no cover

    @abstractmethod
    def handle_events(self,
                      readables: List[Union[int, _HasFileno]],
                      writables: List[Union[int, _HasFileno]]) -> bool:
        """Return True to shutdown work."""
        return False    # pragma: no cover

    @abstractmethod
    def shutdown(self) -> None:
        """Must close any opened resources."""
        pass    # pragma: no cover


class Threadless(multiprocessing.Process):
    """Threadless provides an event loop.  Use it by implementing Threadless class.

    When --threadless option is enabled, each Acceptor process also
    spawns one Threadless process.  And instead of spawning new thread
    for each accepted client connection, Acceptor process sends
    accepted client connection to Threadless process over a pipe.

    ProtocolHandler implements ThreadlessWork class and hooks into the
    event loop provided by Threadless.
    """

    def __init__(
            self,
            client_queue: connection.Connection,
            work_klass: type,
            **kwargs: Any) -> None:
        super().__init__()
        self.client_queue = client_queue
        self.work_klass = work_klass
        self.kwargs = kwargs

        self.works: Dict[int, ThreadlessWork] = {}
        self.selector: Optional[selectors.DefaultSelector] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    @contextlib.contextmanager
    def selected_events(self) -> Generator[Tuple[List[Union[int, _HasFileno]],
                                                 List[Union[int, _HasFileno]]],
                                           None, None]:
        events: Dict[socket.socket, int] = {}
        for work in self.works.values():
            events.update(work.get_events())
        assert self.selector is not None
        for fd in events:
            self.selector.register(fd, events[fd])
        ev = self.selector.select(timeout=1)
        readables = []
        writables = []
        for key, mask in ev:
            if mask & selectors.EVENT_READ:
                readables.append(key.fileobj)
            if mask & selectors.EVENT_WRITE:
                writables.append(key.fileobj)
        yield (readables, writables)
        for fd in events.keys():
            self.selector.unregister(fd)

    async def handle_events(
            self, fileno: int,
            readables: List[Union[int, _HasFileno]],
            writables: List[Union[int, _HasFileno]]) -> bool:
        return self.works[fileno].handle_events(readables, writables)

    # TODO: Use correct future typing annotations
    async def wait_for_tasks(
            self, tasks: Dict[int, Any]) -> None:
        for work_id in tasks:
            # TODO: Resolving one handle_events here can block resolution of other tasks
            try:
                teardown = await asyncio.wait_for(tasks[work_id], DEFAULT_TIMEOUT)
                if teardown:
                    self.cleanup(work_id)
            except asyncio.TimeoutError:
                self.cleanup(work_id)

    def accept_client(self) -> None:
        addr = self.client_queue.recv()
        fileno = recv_handle(self.client_queue)
        self.works[fileno] = self.work_klass(
            fileno=fileno,
            addr=addr,
            **self.kwargs)
        try:
            self.works[fileno].initialize()
            os.close(fileno)
        except ssl.SSLError as e:
            logger.exception('ssl.SSLError', exc_info=e)
            self.cleanup(fileno)

    def cleanup_inactive(self) -> None:
        inactive_works: List[int] = []
        for work_id in self.works:
            if self.works[work_id].is_inactive():
                inactive_works.append(work_id)
        for work_id in inactive_works:
            self.cleanup(work_id)

    def cleanup(self, work_id: int) -> None:
        # TODO: ProtocolHandler.shutdown can call flush which may block
        self.works[work_id].shutdown()
        del self.works[work_id]

    def run_once(self) -> None:
        assert self.loop is not None
        readables: List[Union[int, _HasFileno]] = []
        writables: List[Union[int, _HasFileno]] = []
        with self.selected_events() as (readables, writables):
            if len(readables) == 0 and len(writables) == 0:
                # Remove and shutdown inactive connections
                self.cleanup_inactive()
                return
        # Note that selector from now on is idle,
        # until all the logic below completes.
        #
        # Invoke Threadless.handle_events
        # TODO: Only send readable / writables that client originally registered.
        tasks = {}
        for fileno in self.works:
            tasks[fileno] = self.loop.create_task(
                self.handle_events(fileno, readables, writables))
        # Accepted client connection from Acceptor
        if self.client_queue in readables:
            self.accept_client()
        # Wait for Threadless.handle_events to complete
        self.loop.run_until_complete(self.wait_for_tasks(tasks))
        # Remove and shutdown inactive connections
        self.cleanup_inactive()

    def run(self) -> None:
        try:
            self.selector = selectors.DefaultSelector()
            self.selector.register(self.client_queue, selectors.EVENT_READ)
            self.loop = asyncio.get_event_loop()
            while True:
                self.run_once()
        except KeyboardInterrupt:
            pass
        finally:
            assert self.selector is not None
            self.selector.unregister(self.client_queue)
            self.client_queue.close()
            assert self.loop is not None
            self.loop.close()


class Acceptor(multiprocessing.Process):
    """Socket client acceptor.

    Accepts client connection over received server socket handle and
    starts a new work thread.
    """

    lock = multiprocessing.Lock()

    def __init__(
            self,
            family: socket.AddressFamily,
            threadless: bool,
            work_queue: connection.Connection,
            work_klass: type,
            **kwargs: Any) -> None:
        super().__init__()
        self.family: socket.AddressFamily = family
        self.threadless: bool = threadless
        self.work_queue: connection.Connection = work_queue
        self.work_klass = work_klass
        self.kwargs = kwargs

        self.running = False
        self.selector: Optional[selectors.DefaultSelector] = None
        self.sock: Optional[socket.socket] = None
        self.threadless_process: Optional[multiprocessing.Process] = None
        self.threadless_client_queue: Optional[connection.Connection] = None

    def start_threadless_process(self) -> None:
        if not self.threadless:
            return
        pipe = multiprocessing.Pipe()
        self.threadless_client_queue = pipe[0]
        self.threadless_process = Threadless(
            pipe[1], self.work_klass, **self.kwargs
        )
        # self.threadless_process.daemon = True
        self.threadless_process.start()

    def shutdown_threadless_process(self) -> None:
        if not self.threadless:
            return
        assert self.threadless_process and self.threadless_client_queue
        self.threadless_process.join()
        self.threadless_client_queue.close()

    def run_once(self) -> None:
        assert self.selector
        with self.lock:
            events = self.selector.select(timeout=1)
            if len(events) == 0:
                return
        try:
            assert self.sock
            conn, addr = self.sock.accept()
        except BlockingIOError:
            return
        if self.threadless and \
                self.threadless_client_queue and \
                self.threadless_process:
            self.threadless_client_queue.send(addr)
            send_handle(
                self.threadless_client_queue,
                conn.fileno(),
                self.threadless_process.pid
            )
            conn.close()
        else:
            # Starting a new thread per client request simply means
            # we need 1 million threads to handle a million concurrent
            # connections.  Since most of the client requests are short
            # lived (even with keep-alive), starting threads is excessive.
            work = self.work_klass(
                fileno=conn.fileno(),
                addr=addr,
                **self.kwargs)
            # work.setDaemon(True)
            work.start()

    def run(self) -> None:
        self.running = True
        self.selector = selectors.DefaultSelector()
        fileno = recv_handle(self.work_queue)
        self.sock = socket.fromfd(
            fileno,
            family=self.family,
            type=socket.SOCK_STREAM
        )
        try:
            self.selector.register(self.sock, selectors.EVENT_READ)
            self.start_threadless_process()
            while self.running:
                self.run_once()
        except KeyboardInterrupt:
            pass
        finally:
            self.selector.unregister(self.sock)
            self.shutdown_threadless_process()
            self.sock.close()
            self.work_queue.close()
            self.running = False


class ProtocolException(Exception):
    """Top level ProtocolException exception class.

    All exceptions raised during execution of Http request lifecycle MUST
    inherit ProtocolException base class. Implement response() method
    to optionally return custom response to client."""

    def response(self, request: HttpParser) -> Optional[bytes]:
        return None  # pragma: no cover


class HttpRequestRejected(ProtocolException):
    """Generic exception that can be used to reject the client requests.

    Connections can either be dropped/closed or optionally an
    HTTP status code can be returned."""

    def __init__(self,
                 status_code: Optional[int] = None,
                 reason: Optional[bytes] = None,
                 body: Optional[bytes] = None):
        self.status_code: Optional[int] = status_code
        self.reason: Optional[bytes] = reason
        self.body: Optional[bytes] = body

    def response(self, _request: HttpParser) -> Optional[bytes]:
        pkt = []
        if self.status_code is not None:
            line = HTTP_1_1 + WHITESPACE + bytes_(self.status_code)
            if self.reason:
                line += WHITESPACE + self.reason
            pkt.append(line)
            pkt.append(PROXY_AGENT_HEADER)
        if self.body:
            pkt.append(b'Content-Length: ' + bytes_(len(self.body)))
            pkt.append(CRLF)
            pkt.append(self.body)
        else:
            if len(pkt) > 0:
                pkt.append(CRLF)
        return CRLF.join(pkt) if len(pkt) > 0 else None


class ProxyConnectionFailed(ProtocolException):
    """Exception raised when HttpProxyPlugin is unable to establish connection to upstream server."""

    RESPONSE_PKT = build_http_response(
        httpStatusCodes.BAD_GATEWAY,
        reason=b'Bad Gateway',
        headers={
            PROXY_AGENT_HEADER_KEY: PROXY_AGENT_HEADER_VALUE,
            b'Connection': b'close'
        },
        body=b'Bad Gateway'
    )

    def __init__(self, host: str, port: int, reason: str):
        self.host: str = host
        self.port: int = port
        self.reason: str = reason

    def response(self, _request: HttpParser) -> bytes:
        return self.RESPONSE_PKT


class ProxyAuthenticationFailed(ProtocolException):
    """Exception raised when Http Proxy auth is enabled and
    incoming request doesn't present necessary credentials."""

    RESPONSE_PKT = build_http_response(
        httpStatusCodes.PROXY_AUTH_REQUIRED,
        reason=b'Proxy Authentication Required',
        headers={
            PROXY_AGENT_HEADER_KEY: PROXY_AGENT_HEADER_VALUE,
            b'Proxy-Authenticate': b'Basic',
            b'Connection': b'close',
        },
        body=b'Proxy Authentication Required')

    def response(self, _request: HttpParser) -> bytes:
        return self.RESPONSE_PKT


if TYPE_CHECKING:
    DevtoolsEventQueueType = queue.Queue[Dict[str, Any]]    # pragma: no cover
else:
    DevtoolsEventQueueType = queue.Queue


class ProtocolConfig:
    """Holds various configuration values applicable to ProtocolHandler.

    This config class helps us avoid passing around bunch of key/value pairs across methods.
    """

    ROOT_DATA_DIR_NAME = '.proxy.py'
    GENERATED_CERTS_DIR_NAME = 'certificates'

    def __init__(
            self,
            auth_code: Optional[bytes] = DEFAULT_BASIC_AUTH,
            server_recvbuf_size: int = DEFAULT_SERVER_RECVBUF_SIZE,
            client_recvbuf_size: int = DEFAULT_CLIENT_RECVBUF_SIZE,
            pac_file: Optional[str] = DEFAULT_PAC_FILE,
            pac_file_url_path: Optional[bytes] = DEFAULT_PAC_FILE_URL_PATH,
            plugins: Optional[Dict[bytes, List[type]]] = None,
            disable_headers: Optional[List[bytes]] = None,
            certfile: Optional[str] = None,
            keyfile: Optional[str] = None,
            ca_cert_dir: Optional[str] = None,
            ca_key_file: Optional[str] = None,
            ca_cert_file: Optional[str] = None,
            ca_signing_key_file: Optional[str] = None,
            num_workers: int = 0,
            hostname: Union[ipaddress.IPv4Address,
                            ipaddress.IPv6Address] = DEFAULT_IPV6_HOSTNAME,
            port: int = DEFAULT_PORT,
            backlog: int = DEFAULT_BACKLOG,
            static_server_dir: str = DEFAULT_STATIC_SERVER_DIR,
            enable_static_server: bool = DEFAULT_ENABLE_STATIC_SERVER,
            devtools_event_queue: Optional[DevtoolsEventQueueType] = None,
            devtools_ws_path: bytes = DEFAULT_DEVTOOLS_WS_PATH,
            timeout: int = DEFAULT_TIMEOUT,
            threadless: bool = DEFAULT_THREADLESS) -> None:
        self.threadless = threadless
        self.timeout = timeout
        self.auth_code = auth_code
        self.server_recvbuf_size = server_recvbuf_size
        self.client_recvbuf_size = client_recvbuf_size
        self.pac_file = pac_file
        self.pac_file_url_path = pac_file_url_path
        if plugins is None:
            plugins = {}
        self.plugins: Dict[bytes, List[type]] = plugins
        if disable_headers is None:
            disable_headers = DEFAULT_DISABLE_HEADERS
        self.disable_headers = disable_headers
        self.certfile: Optional[str] = certfile
        self.keyfile: Optional[str] = keyfile
        self.ca_key_file: Optional[str] = ca_key_file
        self.ca_cert_file: Optional[str] = ca_cert_file
        self.ca_signing_key_file: Optional[str] = ca_signing_key_file
        self.num_workers: int = num_workers
        self.hostname: Union[ipaddress.IPv4Address,
                             ipaddress.IPv6Address] = hostname
        self.port: int = port
        self.backlog: int = backlog

        self.enable_static_server: bool = enable_static_server
        self.static_server_dir: str = static_server_dir
        self.devtools_event_queue: Optional[DevtoolsEventQueueType] = devtools_event_queue
        self.devtools_ws_path: bytes = devtools_ws_path

        self.proxy_py_data_dir = os.path.join(
            str(pathlib.Path.home()), self.ROOT_DATA_DIR_NAME)
        os.makedirs(self.proxy_py_data_dir, exist_ok=True)

        self.ca_cert_dir: Optional[str] = ca_cert_dir
        if self.ca_cert_dir is None:
            self.ca_cert_dir = os.path.join(
                self.proxy_py_data_dir, self.GENERATED_CERTS_DIR_NAME)
            os.makedirs(self.ca_cert_dir, exist_ok=True)

    def tls_interception_enabled(self) -> bool:
        return self.ca_key_file is not None and \
            self.ca_cert_dir is not None and \
            self.ca_signing_key_file is not None and \
            self.ca_cert_file is not None

    def encryption_enabled(self) -> bool:
        return self.keyfile is not None and \
            self.certfile is not None


class ProtocolHandlerPlugin(ABC):
    """Base ProtocolHandler Plugin class.

    NOTE: This is an internal plugin and in most cases only useful for core contributors.
    If you are looking for proxy server plugins see `<proxy.HttpProxyBasePlugin>`.

    Implements various lifecycle events for an accepted client connection.
    Following events are of interest:

    1. Client Connection Accepted
       A new plugin instance is created per accepted client connection.
       Add your logic within __init__ constructor for any per connection setup.
    2. Client Request Chunk Received
       on_client_data is called for every chunk of data sent by the client.
    3. Client Request Complete
       on_request_complete is called once client request has completed.
    4. Server Response Chunk Received
       on_response_chunk is called for every chunk received from the server.
    5. Client Connection Closed
       Add your logic within `on_client_connection_close` for any per connection teardown.
    """

    def __init__(
            self,
            config: ProtocolConfig,
            client: TcpClientConnection,
            request: HttpParser):
        self.config: ProtocolConfig = config
        self.client: TcpClientConnection = client
        self.request: HttpParser = request
        super().__init__()

    def name(self) -> str:
        """A unique name for your plugin.

        Defaults to name of the class. This helps plugin developers to directly
        access a specific plugin by its name."""
        return self.__class__.__name__

    @abstractmethod
    def get_descriptors(
            self) -> Tuple[List[socket.socket], List[socket.socket]]:
        return [], []  # pragma: no cover

    @abstractmethod
    def write_to_descriptors(self, w: List[Union[int, _HasFileno]]) -> bool:
        pass  # pragma: no cover

    @abstractmethod
    def read_from_descriptors(self, r: List[Union[int, _HasFileno]]) -> bool:
        pass  # pragma: no cover

    @abstractmethod
    def on_client_data(self, raw: bytes) -> Optional[bytes]:
        return raw  # pragma: no cover

    @abstractmethod
    def on_request_complete(self) -> Union[socket.socket, bool]:
        """Called right after client request parser has reached COMPLETE state."""
        pass  # pragma: no cover

    @abstractmethod
    def on_response_chunk(self, chunk: bytes) -> bytes:
        """Handle data chunks as received from the server.

        Return optionally modified chunk to return back to client."""
        return chunk  # pragma: no cover

    @abstractmethod
    def on_client_connection_close(self) -> None:
        pass  # pragma: no cover


class HttpProxyBasePlugin(ABC):
    """Base HttpProxyPlugin Plugin class.

    Implement various lifecycle event methods to customize behavior."""

    def __init__(
            self,
            config: ProtocolConfig,
            client: TcpClientConnection):
        self.config = config        # pragma: no cover
        self.client = client        # pragma: no cover

    def name(self) -> str:
        """A unique name for your plugin.

        Defaults to name of the class. This helps plugin developers to directly
        access a specific plugin by its name."""
        return self.__class__.__name__      # pragma: no cover

    @abstractmethod
    def before_upstream_connection(self, request: HttpParser) -> Optional[HttpParser]:
        """Handler called just before Proxy upstream connection is established.

        Return optionally modified request object.
        Raise HttpRequestRejected or ProtocolException directly to drop the connection."""
        return request  # pragma: no cover

    @abstractmethod
    def handle_client_request(self, request: HttpParser) -> Optional[HttpParser]:
        """Handler called before dispatching client request to upstream.

        Note: For pipelined (keep-alive) connections, this handler can be
        called multiple times, for each request sent to upstream.

        Note: If TLS interception is enabled, this handler can
        be called multiple times if client exchanges multiple
        requests over same SSL session.

        Return optionally modified request object to dispatch to upstream.
        Return None to drop the request data, e.g. in case a response has already been queued.
        Raise HttpRequestRejected or ProtocolException directly to
            teardown the connection with client.
        """
        return request  # pragma: no cover

    @abstractmethod
    def handle_upstream_chunk(self, chunk: bytes) -> bytes:
        """Handler called right after receiving raw response from upstream server.

        For HTTPS connections, chunk will be encrypted unless
        TLS interception is also enabled."""
        return chunk  # pragma: no cover

    @abstractmethod
    def on_upstream_connection_close(self) -> None:
        """Handler called right after upstream connection has been closed."""
        pass  # pragma: no cover


class HttpProxyPlugin(ProtocolHandlerPlugin):
    """ProtocolHandler plugin which implements HttpProxy specifications."""

    PROXY_TUNNEL_ESTABLISHED_RESPONSE_PKT = build_http_response(
        httpStatusCodes.OK,
        reason=b'Connection established'
    )

    # Used to synchronize with other HttpProxyPlugin instances while
    # generating certificates
    lock = threading.Lock()

    def __init__(
            self,
            config: ProtocolConfig,
            client: TcpClientConnection,
            request: HttpParser):
        super().__init__(config, client, request)
        self.start_time: float = time.time()
        self.server: Optional[TcpServerConnection] = None
        self.response: HttpParser = HttpParser(httpParserTypes.RESPONSE_PARSER)
        self.pipeline_request: Optional[HttpParser] = None
        self.pipeline_response: Optional[HttpParser] = None

        self.plugins: Dict[str, HttpProxyBasePlugin] = {}
        if b'HttpProxyBasePlugin' in self.config.plugins:
            for klass in self.config.plugins[b'HttpProxyBasePlugin']:
                instance = klass(self.config, self.client)
                self.plugins[instance.name()] = instance

    def get_descriptors(
            self) -> Tuple[List[socket.socket], List[socket.socket]]:
        if not self.request.has_upstream_server():
            return [], []

        r: List[socket.socket] = []
        w: List[socket.socket] = []
        if self.server and not self.server.closed and self.server.connection:
            r.append(self.server.connection)
        if self.server and not self.server.closed and \
                self.server.has_buffer() and self.server.connection:
            w.append(self.server.connection)
        return r, w

    def write_to_descriptors(self, w: List[Union[int, _HasFileno]]) -> bool:
        if self.request.has_upstream_server() and \
                self.server and not self.server.closed and \
                self.server.has_buffer() and \
                self.server.connection in w:
            logger.debug('Server is write ready, flushing buffer')
            try:
                self.server.flush()
            except OSError:
                logger.error('OSError when flushing buffer to server')
                return True
            except BrokenPipeError:
                logger.error(
                    'BrokenPipeError when flushing buffer for server')
                return True
        return False

    def read_from_descriptors(self, r: List[Union[int, _HasFileno]]) -> bool:
        if self.request.has_upstream_server(
        ) and self.server and not self.server.closed and self.server.connection in r:
            logger.debug('Server is ready for reads, reading...')
            raw: Optional[bytes] = None

            try:
                raw = self.server.recv(self.config.server_recvbuf_size)
            except ssl.SSLWantReadError:    # Try again later
                # logger.warning('SSLWantReadError encountered while reading from server, will retry ...')
                return False
            except socket.error as e:
                if e.errno == errno.ECONNRESET:
                    logger.warning('Connection reset by upstream: %r' % e)
                else:
                    logger.exception(
                        'Exception while receiving from %s connection %r with reason %r' %
                        (self.server.tag, self.server.connection, e))
                return True

            if not raw:
                logger.debug('Server closed connection, tearing down...')
                return True

            for plugin in self.plugins.values():
                raw = plugin.handle_upstream_chunk(raw)

            # parse incoming response packet
            # only for non-https requests and when
            # tls interception is enabled
            if self.request.method != httpMethods.CONNECT:
                # See https://github.com/abhinavsingh/proxy.py/issues/127 for why
                # currently response parsing is disabled when TLS interception is enabled.
                #
                # or self.config.tls_interception_enabled():
                if self.response.state == httpParserStates.COMPLETE:
                    if self.pipeline_response is None:
                        self.pipeline_response = HttpParser(httpParserTypes.RESPONSE_PARSER)
                    self.pipeline_response.parse(raw)
                    if self.pipeline_response.state == httpParserStates.COMPLETE:
                        self.pipeline_response = None
                else:
                    self.response.parse(raw)
            else:
                self.response.total_size += len(raw)
            # queue raw data for client
            self.client.queue(raw)
        return False

    def access_log(self) -> None:
        server_host, server_port = self.server.addr if self.server else (
            None, None)
        connection_time_ms = (time.time() - self.start_time) * 1000
        if self.request.method == b'CONNECT':
            logger.info(
                '%s:%s - %s %s:%s - %s bytes - %.2f ms' %
                (self.client.addr[0],
                 self.client.addr[1],
                 text_(self.request.method),
                 text_(server_host),
                 text_(server_port),
                 self.response.total_size,
                 connection_time_ms))
        elif self.request.method:
            logger.info(
                '%s:%s - %s %s:%s%s - %s %s - %s bytes - %.2f ms' %
                (self.client.addr[0], self.client.addr[1],
                 text_(self.request.method),
                 text_(server_host), server_port,
                 text_(self.request.path),
                 text_(self.response.code),
                 text_(self.response.reason),
                 self.response.total_size,
                 connection_time_ms))

    def on_client_connection_close(self) -> None:
        if not self.request.has_upstream_server():
            return

        self.access_log()

        # If server was never initialized, return
        if self.server is None:
            return

        # Note that, server instance was initialized
        # but not necessarily the connection object exists.
        # Invoke plugin.on_upstream_connection_close
        for plugin in self.plugins.values():
            plugin.on_upstream_connection_close()

        try:
            try:
                self.server.connection.shutdown(socket.SHUT_WR)
            except OSError:
                pass
            finally:
                # TODO: Unwrap if wrapped before close?
                self.server.connection.close()
        except TcpConnectionUninitializedException:
            pass
        finally:
            logger.debug(
                'Closed server connection with pending server buffer size %d bytes' %
                self.server.buffer_size())

    def on_response_chunk(self, chunk: bytes) -> bytes:
        # TODO: Allow to output multiple access_log lines
        # for each request over a pipelined HTTP connection (not for HTTPS).
        # However, this must also be accompanied by resetting both request
        # and response objects.
        #
        # if not self.request.method == httpMethods.CONNECT and \
        #         self.response.state == httpParserStates.COMPLETE:
        #     self.access_log()
        return chunk

    def on_client_data(self, raw: bytes) -> Optional[bytes]:
        if not self.request.has_upstream_server():
            return raw

        if self.server and not self.server.closed:
            if self.request.state == httpParserStates.COMPLETE and (
                    self.request.method != httpMethods.CONNECT or
                    self.config.tls_interception_enabled()):
                if self.pipeline_request is None:
                    self.pipeline_request = HttpParser(httpParserTypes.REQUEST_PARSER)
                self.pipeline_request.parse(raw)
                if self.pipeline_request.state == httpParserStates.COMPLETE:
                    for plugin in self.plugins.values():
                        assert self.pipeline_request is not None
                        r = plugin.handle_client_request(self.pipeline_request)
                        if r is None:
                            return None
                        self.pipeline_request = r
                    assert self.pipeline_request is not None
                    self.server.queue(self.pipeline_request.build())
                    self.pipeline_request = None
            else:
                self.server.queue(raw)
            return None
        else:
            return raw

    @staticmethod
    def generated_cert_file_path(ca_cert_dir: str, host: str) -> str:
        return os.path.join(ca_cert_dir, '%s.pem' % host)

    def generate_upstream_certificate(self, _certificate: Optional[Dict[str, Any]]) -> str:
        if not (self.config.ca_cert_dir and self.config.ca_signing_key_file and
                self.config.ca_cert_file and self.config.ca_key_file):
            raise ProtocolException(
                f'For certificate generation all the following flags are mandatory: '
                f'--ca-cert-file:{ self.config.ca_cert_file }, '
                f'--ca-key-file:{ self.config.ca_key_file }, '
                f'--ca-signing-key-file:{ self.config.ca_signing_key_file }')
        cert_file_path = HttpProxyPlugin.generated_cert_file_path(
            self.config.ca_cert_dir, text_(self.request.host))
        with self.lock:
            if not os.path.isfile(cert_file_path):
                logger.debug('Generating certificates %s', cert_file_path)
                # TODO: Parse subject from certificate
                # Currently we only set CN= field for generated certificates.
                gen_cert = subprocess.Popen(
                    ['openssl', 'req', '-new', '-key', self.config.ca_signing_key_file, '-subj',
                     f'/C=/ST=/L=/O=/OU=/CN={ text_(self.request.host) }'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
                sign_cert = subprocess.Popen(
                    ['openssl', 'x509', '-req', '-days', '365', '-CA', self.config.ca_cert_file, '-CAkey',
                     self.config.ca_key_file, '-set_serial', str(int(time.time())), '-out', cert_file_path],
                    stdin=gen_cert.stdout,
                    stderr=subprocess.PIPE)
                # TODO: Ensure sign_cert success.
                sign_cert.communicate(timeout=10)
        return cert_file_path

    def wrap_server(self) -> None:
        assert self.server is not None
        assert isinstance(self.server.connection, socket.socket)
        ctx = ssl.create_default_context(
            ssl.Purpose.SERVER_AUTH)
        ctx.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
        self.server.connection.setblocking(True)
        self.server._conn = ctx.wrap_socket(
            self.server.connection,
            server_hostname=text_(self.request.host))
        self.server.connection.setblocking(False)

    def wrap_client(self) -> None:
        assert self.server is not None
        assert isinstance(self.server.connection, ssl.SSLSocket)
        generated_cert = self.generate_upstream_certificate(
            cast(Dict[str, Any], self.server.connection.getpeercert()))
        self.client.connection.setblocking(True)
        self.client.flush()
        self.client._conn = ssl.wrap_socket(
            self.client.connection,
            server_side=True,
            keyfile=self.config.ca_signing_key_file,
            certfile=generated_cert)
        self.client.connection.setblocking(False)
        logger.debug(
            'TLS interception using %s', generated_cert)

    def on_request_complete(self) -> Union[socket.socket, bool]:
        if not self.request.has_upstream_server():
            return False

        self.authenticate()

        # Note: can raise HttpRequestRejected exception
        # Invoke plugin.before_upstream_connection
        do_connect = True
        for plugin in self.plugins.values():
            r = plugin.before_upstream_connection(self.request)
            if r is None:
                do_connect = False
                break
            self.request = r

        if do_connect:
            self.connect_upstream()

        for plugin in self.plugins.values():
            assert self.request is not None
            r = plugin.handle_client_request(self.request)
            if r is not None:
                self.request = r
            else:
                return False

        if self.request.method == httpMethods.CONNECT:
            self.client.queue(
                HttpProxyPlugin.PROXY_TUNNEL_ESTABLISHED_RESPONSE_PKT)
            # If interception is enabled
            if self.config.tls_interception_enabled():
                # Perform SSL/TLS handshake with upstream
                self.wrap_server()
                # Generate certificate and perform handshake with client
                try:
                    # wrap_client also flushes client data before wrapping
                    # sending to client can raise, handle expected exceptions
                    self.wrap_client()
                except OSError:
                    logger.error('OSError when wrapping client')
                    return True
                except BrokenPipeError:
                    logger.error(
                        'BrokenPipeError when wrapping client')
                    return True
                # Update all plugin connection reference
                for plugin in self.plugins.values():
                    plugin.client._conn = self.client.connection
                return self.client.connection
        elif self.server:
            # - proxy-connection header is a mistake, it doesn't seem to be
            #   officially documented in any specification, drop it.
            # - proxy-authorization is of no use for upstream, remove it.
            self.request.del_headers(
                [b'proxy-authorization', b'proxy-connection'])
            # - For HTTP/1.0, connection header defaults to close
            # - For HTTP/1.1, connection header defaults to keep-alive
            # Respect headers sent by client instead of manipulating
            # Connection or Keep-Alive header.  However, note that per
            # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Connection
            # connection headers are meant for communication between client and
            # first intercepting proxy.
            self.request.add_headers([(b'Via', b'1.1 %s' % PROXY_AGENT_HEADER_VALUE)])
            # Disable args.disable_headers before dispatching to upstream
            self.server.queue(
                self.request.build(
                    disable_headers=self.config.disable_headers))
        return False

    def authenticate(self) -> None:
        if self.config.auth_code:
            if b'proxy-authorization' not in self.request.headers or \
                    self.request.headers[b'proxy-authorization'][1] != self.config.auth_code:
                raise ProxyAuthenticationFailed()

    def connect_upstream(self) -> None:
        host, port = self.request.host, self.request.port
        if host and port:
            self.server = TcpServerConnection(text_(host), port)
            try:
                logger.debug(
                    'Connecting to upstream %s:%s' %
                    (text_(host), port))
                self.server.connect()
                self.server.connection.setblocking(False)
                logger.debug(
                    'Connected to upstream %s:%s' %
                    (text_(host), port))
            except Exception as e:  # TimeoutError, socket.gaierror
                self.server.closed = True
                raise ProxyConnectionFailed(text_(host), port, repr(e)) from e
        else:
            logger.exception('Both host and port must exist')
            raise ProtocolException()


class WebsocketFrame:
    """Websocket frames parser and constructor."""

    GUID = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

    def __init__(self) -> None:
        self.fin: bool = False
        self.rsv1: bool = False
        self.rsv2: bool = False
        self.rsv3: bool = False
        self.opcode: int = 0
        self.masked: bool = False
        self.payload_length: Optional[int] = None
        self.mask: Optional[bytes] = None
        self.data: Optional[bytes] = None

    def reset(self) -> None:
        self.fin = False
        self.rsv1 = False
        self.rsv2 = False
        self.rsv3 = False
        self.opcode = 0
        self.masked = False
        self.payload_length = None
        self.mask = None
        self.data = None

    def parse_fin_and_rsv(self, byte: int) -> None:
        self.fin = bool(byte & 1 << 7)
        self.rsv1 = bool(byte & 1 << 6)
        self.rsv2 = bool(byte & 1 << 5)
        self.rsv3 = bool(byte & 1 << 4)
        self.opcode = byte & 0b00001111

    def parse_mask_and_payload(self, byte: int) -> None:
        self.masked = bool(byte & 0b10000000)
        self.payload_length = byte & 0b01111111

    def build(self) -> bytes:
        if self.payload_length is None and self.data:
            self.payload_length = len(self.data)
        raw = io.BytesIO()
        raw.write(
            struct.pack(
                '!B',
                (1 << 7 if self.fin else 0) |
                (1 << 6 if self.rsv1 else 0) |
                (1 << 5 if self.rsv2 else 0) |
                (1 << 4 if self.rsv3 else 0) |
                self.opcode
            ))
        assert self.payload_length is not None
        if self.payload_length < 126:
            raw.write(
                struct.pack(
                    '!B',
                    (1 << 7 if self.masked else 0) | self.payload_length
                )
            )
        elif self.payload_length < 1 << 16:
            raw.write(
                struct.pack(
                    '!BH',
                    (1 << 7 if self.masked else 0) | 126,
                    self.payload_length
                )
            )
        elif self.payload_length < 1 << 64:
            raw.write(
                struct.pack(
                    '!BHQ',
                    (1 << 7 if self.masked else 0) | 127,
                    self.payload_length
                )
            )
        else:
            raise ValueError(f'Invalid payload_length { self.payload_length },'
                             f'maximum allowed { 1 << 64 }')
        if self.masked and self.data:
            mask = secrets.token_bytes(4) if self.mask is None else self.mask
            raw.write(mask)
            raw.write(self.apply_mask(self.data, mask))
        elif self.data:
            raw.write(self.data)
        return raw.getvalue()

    def parse(self, raw: bytes) -> bytes:
        cur = 0
        self.parse_fin_and_rsv(raw[cur])
        cur += 1

        self.parse_mask_and_payload(raw[cur])
        cur += 1

        if self.payload_length == 126:
            data = raw[cur: cur + 2]
            self.payload_length, = struct.unpack('!H', data)
            cur += 2
        elif self.payload_length == 127:
            data = raw[cur: cur + 8]
            self.payload_length, = struct.unpack('!Q', data)
            cur += 8

        if self.masked:
            self.mask = raw[cur: cur + 4]
            cur += 4

        assert self.payload_length
        self.data = raw[cur: cur + self.payload_length]
        cur += self.payload_length
        if self.masked:
            assert self.mask is not None
            self.data = self.apply_mask(self.data, self.mask)

        return raw[cur:]

    @staticmethod
    def apply_mask(data: bytes, mask: bytes) -> bytes:
        raw = bytearray(data)
        for i in range(len(raw)):
            raw[i] = raw[i] ^ mask[i % 4]
        return bytes(raw)

    @staticmethod
    def key_to_accept(key: bytes) -> bytes:
        sha1 = hashlib.sha1()
        sha1.update(key + WebsocketFrame.GUID)
        return base64.b64encode(sha1.digest())


class WebsocketClient(TcpConnection):

    def __init__(self,
                 hostname: Union[ipaddress.IPv4Address, ipaddress.IPv6Address],
                 port: int,
                 path: bytes = b'/',
                 on_message: Optional[Callable[[WebsocketFrame], None]] = None) -> None:
        super().__init__(tcpConnectionTypes.CLIENT)
        self.hostname: Union[ipaddress.IPv4Address, ipaddress.IPv6Address] = hostname
        self.port: int = port
        self.path: bytes = path
        self.sock: socket.socket = new_socket_connection((str(self.hostname), self.port))
        self.on_message: Optional[Callable[[WebsocketFrame], None]] = on_message
        self.upgrade()
        self.sock.setblocking(False)
        self.selector: selectors.DefaultSelector = selectors.DefaultSelector()

    @property
    def connection(self) -> Union[ssl.SSLSocket, socket.socket]:
        return self.sock

    def upgrade(self) -> None:
        key = base64.b64encode(secrets.token_bytes(16))
        self.sock.send(build_websocket_handshake_request(key, url=self.path))
        response = HttpParser(httpParserTypes.RESPONSE_PARSER)
        response.parse(self.sock.recv(DEFAULT_BUFFER_SIZE))
        accept = response.header(b'Sec-Websocket-Accept')
        assert WebsocketFrame.key_to_accept(key) == accept

    def ping(self, data: Optional[bytes] = None) -> None:
        pass

    def pong(self, data: Optional[bytes] = None) -> None:
        pass

    def shutdown(self, _data: Optional[bytes] = None) -> None:
        """Closes connection with the server."""
        super().close()

    def run_once(self) -> bool:
        ev = selectors.EVENT_READ
        if self.has_buffer():
            ev |= selectors.EVENT_WRITE
        self.selector.register(self.sock.fileno(), ev)
        events = self.selector.select(timeout=1)
        self.selector.unregister(self.sock)
        for key, mask in events:
            if mask & selectors.EVENT_READ and self.on_message:
                raw = self.recv()
                if raw is None or raw == b'':
                    self.closed = True
                    logger.debug('Websocket connection closed by server')
                    return True
                frame = WebsocketFrame()
                frame.parse(raw)
                self.on_message(frame)
            elif mask & selectors.EVENT_WRITE:
                logger.debug(self.buffer)
                self.flush()
        return False

    def run(self) -> None:
        logger.debug('running')
        try:
            while not self.closed:
                teardown = self.run_once()
                if teardown:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            try:
                self.selector.unregister(self.sock)
                self.sock.shutdown(socket.SHUT_WR)
            except Exception as e:
                logging.exception('Exception while shutdown of websocket client', exc_info=e)
            self.sock.close()
        logger.info('done')


class HttpWebServerBasePlugin(ABC):
    """Web Server Plugin for routing of requests."""

    def __init__(
            self,
            config: ProtocolConfig,
            client: TcpClientConnection):
        self.config = config
        self.client = client

    @abstractmethod
    def routes(self) -> List[Tuple[int, bytes]]:
        """Return List(protocol, path) that this plugin handles."""
        raise NotImplementedError()     # pragma: no cover

    @abstractmethod
    def handle_request(self, request: HttpParser) -> None:
        """Handle the request and serve response."""
        raise NotImplementedError()     # pragma: no cover

    @abstractmethod
    def on_websocket_open(self) -> None:
        """Called when websocket handshake has finished."""
        raise NotImplementedError()     # pragma: no cover

    @abstractmethod
    def on_websocket_message(self, frame: WebsocketFrame) -> None:
        """Handle websocket frame."""
        raise NotImplementedError()     # pragma: no cover

    @abstractmethod
    def on_websocket_close(self) -> None:
        """Called when websocket connection has been closed."""
        raise NotImplementedError()     # pragma: no cover


class DevtoolsWebsocketPlugin(HttpWebServerBasePlugin):
    """DevtoolsWebsocketPlugin handles Devtools Frontend websocket requests.

    For every connected Devtools Frontend instance, a dispatcher thread is
    started which drains the global Devtools protocol events queue.

    Dispatcher thread is terminated when Devtools Frontend disconnects."""

    def __init__(
            self,
            config: ProtocolConfig,
            client: TcpClientConnection):
        super().__init__(config, client)
        self.event_dispatcher_thread: Optional[threading.Thread] = None
        self.event_dispatcher_shutdown: Optional[threading.Event] = None

    def start_dispatcher(self) -> None:
        self.event_dispatcher_shutdown = threading.Event()
        assert self.config.devtools_event_queue is not None
        self.event_dispatcher_thread = threading.Thread(
            target=DevtoolsWebsocketPlugin.event_dispatcher,
            args=(self.event_dispatcher_shutdown,
                  self.config.devtools_event_queue,
                  self.client))
        # self.event_dispatcher_thread.setDaemon(True)
        self.event_dispatcher_thread.start()

    def stop_dispatcher(self) -> None:
        assert self.event_dispatcher_shutdown is not None
        assert self.event_dispatcher_thread is not None
        self.event_dispatcher_shutdown.set()
        self.event_dispatcher_thread.join()
        logger.debug('Event dispatcher shutdown')

    @staticmethod
    def event_dispatcher(
            shutdown: threading.Event,
            devtools_event_queue: DevtoolsEventQueueType,
            client: TcpClientConnection) -> None:
        while not shutdown.is_set():
            try:
                ev = devtools_event_queue.get(timeout=1)
                frame = WebsocketFrame()
                frame.fin = True
                frame.opcode = websocketOpcodes.TEXT_FRAME
                frame.data = bytes_(json.dumps(ev))
                logger.debug(ev)
                client.queue(frame.build())
            except queue.Empty:
                pass
            except Exception as e:
                logger.exception('Event dispatcher exception', exc_info=e)
                break
            except KeyboardInterrupt:
                break

    def routes(self) -> List[Tuple[int, bytes]]:
        return [
            (httpProtocolTypes.WEBSOCKET, self.config.devtools_ws_path)
        ]

    def handle_request(self, request: HttpParser) -> None:
        pass

    def on_websocket_open(self) -> None:
        self.start_dispatcher()

    def on_websocket_message(self, frame: WebsocketFrame) -> None:
        if frame.data:
            message = json.loads(frame.data)
            self.handle_message(message)
        else:
            logger.debug('No data found in frame')

    def on_websocket_close(self) -> None:
        self.stop_dispatcher()

    def handle_message(self, message: Dict[str, Any]) -> None:
        frame = WebsocketFrame()
        frame.fin = True
        frame.opcode = websocketOpcodes.TEXT_FRAME

        if message['method'] in (
            'Page.canScreencast',
            'Network.canEmulateNetworkConditions',
            'Emulation.canEmulate'
        ):
            data = json.dumps({
                'id': message['id'],
                'result': False
            })
        elif message['method'] == 'Page.getResourceTree':
            data = json.dumps({
                'id': message['id'],
                'result': {
                    'frameTree': {
                        'frame': {
                            'id': 1,
                            'url': 'http://proxypy',
                            'mimeType': 'other',
                        },
                        'childFrames': [],
                        'resources': []
                    }
                }
            })
        elif message['method'] == 'Network.getResponseBody':
            logger.debug('received request method Network.getResponseBody')
            data = json.dumps({
                'id': message['id'],
                'result': {
                    'body': '',
                    'base64Encoded': False,
                }
            })
        else:
            data = json.dumps({
                'id': message['id'],
                'result': {},
            })

        frame.data = bytes_(data)
        self.client.queue(frame.build())


class HttpWebServerPacFilePlugin(HttpWebServerBasePlugin):

    def __init__(
            self,
            config: ProtocolConfig,
            client: TcpClientConnection):
        super().__init__(config, client)
        self.pac_file_response: Optional[bytes] = None
        self.cache_pac_file_response()

    def cache_pac_file_response(self) -> None:
        if self.config.pac_file:
            try:
                with open(self.config.pac_file, 'rb') as f:
                    content = f.read()
            except IOError:
                content = bytes_(self.config.pac_file)
            self.pac_file_response = build_http_response(
                200, reason=b'OK', headers={
                    b'Content-Type': b'application/x-ns-proxy-autoconfig',
                }, body=content
            )

    def routes(self) -> List[Tuple[int, bytes]]:
        if self.config.pac_file_url_path:
            return [
                (httpProtocolTypes.HTTP, bytes_(self.config.pac_file_url_path)),
                (httpProtocolTypes.HTTPS, bytes_(self.config.pac_file_url_path)),
            ]
        return []   # pragma: no cover

    def handle_request(self, request: HttpParser) -> None:
        if self.config.pac_file and self.pac_file_response:
            self.client.queue(self.pac_file_response)

    def on_websocket_open(self) -> None:
        pass    # pragma: no cover

    def on_websocket_message(self, frame: WebsocketFrame) -> None:
        pass    # pragma: no cover

    def on_websocket_close(self) -> None:
        pass    # pragma: no cover


class HttpWebServerPlugin(ProtocolHandlerPlugin):
    """ProtocolHandler plugin which handles incoming requests to local web server."""

    DEFAULT_404_RESPONSE = build_http_response(
        httpStatusCodes.NOT_FOUND,
        reason=b'NOT FOUND',
        headers={b'Server': PROXY_AGENT_HEADER_VALUE,
                 b'Connection': b'close'}
    )

    DEFAULT_501_RESPONSE = build_http_response(
        httpStatusCodes.NOT_IMPLEMENTED,
        reason=b'NOT IMPLEMENTED',
        headers={b'Server': PROXY_AGENT_HEADER_VALUE,
                 b'Connection': b'close'}
    )

    def __init__(
            self,
            config: ProtocolConfig,
            client: TcpClientConnection,
            request: HttpParser):
        super().__init__(config, client, request)
        self.start_time: float = time.time()
        self.pipeline_request: Optional[HttpParser] = None
        self.switched_protocol: Optional[int] = None
        self.routes: Dict[int, Dict[bytes, HttpWebServerBasePlugin]] = {
            httpProtocolTypes.HTTP: {},
            httpProtocolTypes.HTTPS: {},
            httpProtocolTypes.WEBSOCKET: {},
        }
        self.route: Optional[HttpWebServerBasePlugin] = None

        if b'HttpWebServerBasePlugin' in self.config.plugins:
            for klass in self.config.plugins[b'HttpWebServerBasePlugin']:
                instance = klass(self.config, self.client)
                for (protocol, path) in instance.routes():
                    self.routes[protocol][path] = instance

    def serve_file_or_404(self, path: str) -> bool:
        """Read and serves a file from disk.

        Queues 404 Not Found for IOError.
        Shouldn't this be server error?
        """
        try:
            with open(path, 'rb') as f:
                content = f.read()
            content_type = mimetypes.guess_type(path)[0]
            if content_type is None:
                content_type = 'text/plain'
            self.client.queue(build_http_response(
                httpStatusCodes.OK,
                reason=b'OK',
                headers={
                    b'Content-Type': bytes_(content_type),
                },
                body=content))
            return False
        except IOError:
            self.client.queue(self.DEFAULT_404_RESPONSE)
        return True

    def try_upgrade(self) -> bool:
        if self.request.has_header(b'connection') and \
                self.request.header(b'connection').lower() == b'upgrade':
            if self.request.has_header(b'upgrade') and \
                    self.request.header(b'upgrade').lower() == b'websocket':
                self.client.queue(
                    build_websocket_handshake_response(
                        WebsocketFrame.key_to_accept(
                            self.request.header(b'Sec-WebSocket-Key'))))
                self.switched_protocol = httpProtocolTypes.WEBSOCKET
            else:
                self.client.queue(self.DEFAULT_501_RESPONSE)
                return True
        return False

    def on_request_complete(self) -> Union[socket.socket, bool]:
        if self.request.has_upstream_server():
            return False

        # If a websocket route exists for the path, try upgrade
        if self.request.path in self.routes[httpProtocolTypes.WEBSOCKET]:
            self.route = self.routes[httpProtocolTypes.WEBSOCKET][self.request.path]

            # Connection upgrade
            teardown = self.try_upgrade()
            if teardown:
                return True

            # For upgraded connections, nothing more to do
            if self.switched_protocol:
                # Invoke plugin.on_websocket_open
                self.route.on_websocket_open()
                return False

        # Routing for Http(s) requests
        protocol = httpProtocolTypes.HTTPS \
            if self.config.encryption_enabled() else \
            httpProtocolTypes.HTTP
        for r in self.routes[protocol]:
            if r == self.request.path:
                self.route = self.routes[protocol][r]
                self.route.handle_request(self.request)
                return False

        # No-route found, try static serving if enabled
        if self.config.enable_static_server:
            path = text_(self.request.path).split('?')[0]
            if os.path.isfile(self.config.static_server_dir + path):
                return self.serve_file_or_404(self.config.static_server_dir + path)

        # Catch all unhandled web server requests, return 404
        self.client.queue(self.DEFAULT_404_RESPONSE)
        return True

    def write_to_descriptors(self, w: List[Union[int, _HasFileno]]) -> bool:
        pass

    def read_from_descriptors(self, r: List[Union[int, _HasFileno]]) -> bool:
        pass

    def on_client_data(self, raw: bytes) -> Optional[bytes]:
        if self.switched_protocol == httpProtocolTypes.WEBSOCKET:
            remaining = raw
            frame = WebsocketFrame()
            while remaining != b'':
                # TODO: Teardown if invalid protocol exception
                remaining = frame.parse(remaining)
                for r in self.routes[httpProtocolTypes.WEBSOCKET]:
                    if r == self.request.path:
                        self.routes[httpProtocolTypes.WEBSOCKET][r].on_websocket_message(frame)
                frame.reset()
            return None
        # If 1st valid request was completed and it's a HTTP/1.1 keep-alive
        # And only if we have a route, parse pipeline requests
        elif self.request.state == httpParserStates.COMPLETE and \
                self.request.is_http_1_1_keep_alive() and \
                self.route is not None:
            if self.pipeline_request is None:
                self.pipeline_request = HttpParser(httpParserTypes.REQUEST_PARSER)
            self.pipeline_request.parse(raw)
            if self.pipeline_request.state == httpParserStates.COMPLETE:
                self.route.handle_request(self.pipeline_request)
                if not self.pipeline_request.is_http_1_1_keep_alive():
                    logger.error('Pipelined request is not keep-alive, will teardown request...')
                    raise ProtocolException()
                self.pipeline_request = None
        return raw

    def on_response_chunk(self, chunk: bytes) -> bytes:
        return chunk

    def on_client_connection_close(self) -> None:
        if self.request.has_upstream_server():
            return
        if self.switched_protocol:
            # Invoke plugin.on_websocket_close
            for r in self.routes[httpProtocolTypes.WEBSOCKET]:
                if r == self.request.path:
                    self.routes[httpProtocolTypes.WEBSOCKET][r].on_websocket_close()
        self.access_log()

    def access_log(self) -> None:
        logger.info(
            '%s:%s - %s %s - %.2f ms' %
            (self.client.addr[0],
             self.client.addr[1],
             text_(self.request.method),
             text_(self.request.path),
             (time.time() - self.start_time) * 1000))

    def get_descriptors(
            self) -> Tuple[List[socket.socket], List[socket.socket]]:
        return [], []


class ProtocolHandler(threading.Thread, ThreadlessWork):
    """HTTP, HTTPS, HTTP2, WebSockets protocol handler.

    Accepts `Client` connection object and manages ProtocolHandlerPlugin invocations.
    """

    def __init__(self, fileno: int, addr: Tuple[str, int],
                 config: Optional[ProtocolConfig] = None):
        super().__init__()
        self.fileno: int = fileno
        self.addr: Tuple[str, int] = addr

        self.start_time: float = time.time()
        self.last_activity: float = self.start_time

        self.config: ProtocolConfig = config if config else ProtocolConfig()
        self.request: HttpParser = HttpParser(httpParserTypes.REQUEST_PARSER)
        self.response: HttpParser = HttpParser(httpParserTypes.RESPONSE_PARSER)

        self.selector = selectors.DefaultSelector()
        self.client: TcpClientConnection = TcpClientConnection(
            self.fromfd(self.fileno), self.addr
        )
        self.plugins: Dict[str, ProtocolHandlerPlugin] = {}

    def initialize(self) -> None:
        """Optionally upgrades connection to HTTPS, set conn in non-blocking mode and initializes plugins."""
        conn = self.optionally_wrap_socket(self.client.connection)
        conn.setblocking(False)
        if self.config.encryption_enabled():
            self.client = TcpClientConnection(conn=conn, addr=self.addr)
        if b'ProtocolHandlerPlugin' in self.config.plugins:
            for klass in self.config.plugins[b'ProtocolHandlerPlugin']:
                instance = klass(self.config, self.client, self.request)
                self.plugins[instance.name()] = instance
        logger.debug('Handling connection %r' % self.client.connection)

    def is_inactive(self) -> bool:
        if not self.client.has_buffer() and \
                self.connection_inactive_for() > self.config.timeout:
            return True
        return False

    def get_events(self) -> Dict[socket.socket, int]:
        events: Dict[socket.socket, int] = {
            self.client.connection: selectors.EVENT_READ
        }
        if self.client.has_buffer():
            events[self.client.connection] |= selectors.EVENT_WRITE

        # ProtocolHandlerPlugin.get_descriptors
        for plugin in self.plugins.values():
            plugin_read_desc, plugin_write_desc = plugin.get_descriptors()
            for r in plugin_read_desc:
                if r not in events:
                    events[r] = selectors.EVENT_READ
                else:
                    events[r] |= selectors.EVENT_READ
            for w in plugin_write_desc:
                if w not in events:
                    events[w] = selectors.EVENT_WRITE
                else:
                    events[w] |= selectors.EVENT_WRITE

        return events

    def handle_events(
            self,
            readables: List[Union[int, _HasFileno]],
            writables: List[Union[int, _HasFileno]]) -> bool:
        """Returns True if proxy must teardown."""
        # Flush buffer for ready to write sockets
        teardown = self.handle_writables(writables)
        if teardown:
            return True

        # Invoke plugin.write_to_descriptors
        for plugin in self.plugins.values():
            teardown = plugin.write_to_descriptors(writables)
            if teardown:
                return True

        # Read from ready to read sockets
        teardown = self.handle_readables(readables)
        if teardown:
            return True

        # Invoke plugin.read_from_descriptors
        for plugin in self.plugins.values():
            teardown = plugin.read_from_descriptors(readables)
            if teardown:
                return True

        return False

    def shutdown(self) -> None:
        # Flush pending buffer if any
        self.flush()

        # Invoke plugin.on_client_connection_close
        for plugin in self.plugins.values():
            plugin.on_client_connection_close()

        logger.debug(
            'Closing client connection %r '
            'at address %r with pending client buffer size %d bytes' %
            (self.client.connection, self.client.addr, self.client.buffer_size()))

        conn = self.client.connection
        try:
            # Unwrap if wrapped before shutdown.
            if self.config.encryption_enabled() and \
                    isinstance(self.client.connection, ssl.SSLSocket):
                conn = self.client.connection.unwrap()
            conn.shutdown(socket.SHUT_WR)
            logger.debug('Client connection shutdown successful')
        except OSError:
            pass
        finally:
            conn.close()
            logger.debug('Client connection closed')

    def fromfd(self, fileno: int) -> socket.socket:
        conn = socket.fromfd(
            fileno, family=socket.AF_INET if self.config.hostname.version == 4 else socket.AF_INET6,
            type=socket.SOCK_STREAM)
        return conn

    def optionally_wrap_socket(
            self, conn: socket.socket) -> Union[ssl.SSLSocket, socket.socket]:
        """Attempts to wrap accepted client connection using provided certificates.

        Shutdown and closes client connection upon error.
        """
        if self.config.encryption_enabled():
            ctx = ssl.create_default_context(
                ssl.Purpose.CLIENT_AUTH)
            ctx.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
            ctx.verify_mode = ssl.CERT_NONE
            assert self.config.keyfile and self.config.certfile
            ctx.load_cert_chain(
                certfile=self.config.certfile,
                keyfile=self.config.keyfile)
            conn = ctx.wrap_socket(conn, server_side=True)
        return conn

    def connection_inactive_for(self) -> float:
        return time.time() - self.last_activity

    def flush(self) -> None:
        if not self.client.has_buffer():
            return
        try:
            self.selector.register(self.client.connection, selectors.EVENT_WRITE)
            while self.client.has_buffer():
                ev: List[Tuple[selectors.SelectorKey, int]] = self.selector.select(timeout=1)
                if len(ev) == 0:
                    continue
                self.client.flush()
        except BrokenPipeError:
            pass
        finally:
            self.selector.unregister(self.client.connection)

    def handle_writables(self, writables: List[Union[int, _HasFileno]]) -> bool:
        if self.client.buffer_size() > 0 and self.client.connection in writables:
            logger.debug('Client is ready for writes, flushing buffer')
            self.last_activity = time.time()

            # Invoke plugin.on_response_chunk
            chunk = self.client.buffer
            for plugin in self.plugins.values():
                chunk = plugin.on_response_chunk(chunk)
                if chunk is None:
                    break

            try:
                self.client.flush()
            except OSError:
                logger.error('OSError when flushing buffer to client')
                return True
            except BrokenPipeError:
                logger.error(
                    'BrokenPipeError when flushing buffer for client')
                return True
        return False

    def handle_readables(self, readables: List[Union[int, _HasFileno]]) -> bool:
        if self.client.connection in readables:
            logger.debug('Client is ready for reads, reading')
            self.last_activity = time.time()
            client_data: Optional[bytes] = None

            try:
                client_data = self.client.recv(self.config.client_recvbuf_size)
            except ssl.SSLWantReadError:    # Try again later
                logger.warning('SSLWantReadError encountered while reading from client, will retry ...')
                return False
            except socket.error as e:
                if e.errno == errno.ECONNRESET:
                    logger.warning('%r' % e)
                else:
                    logger.exception(
                        'Exception while receiving from %s connection %r with reason %r' %
                        (self.client.tag, self.client.connection, e))
                return True

            if not client_data:
                logger.debug('Client closed connection, tearing down...')
                self.client.closed = True
                return True

            try:
                # ProtocolHandlerPlugin.on_client_data
                # Can raise ProtocolException to teardown the connection
                plugin_index = 0
                plugins = list(self.plugins.values())
                while plugin_index < len(plugins) and client_data:
                    client_data = plugins[plugin_index].on_client_data(client_data)
                    if client_data is None:
                        break
                    plugin_index += 1

                # Don't parse request any further after 1st request has completed.
                # This specially does happen for pipeline requests.
                # Plugins can utilize on_client_data for such cases and
                # apply custom logic to handle request data sent after 1st valid request.
                if client_data and self.request.state != httpParserStates.COMPLETE:
                    # Parse http request
                    self.request.parse(client_data)
                    if self.request.state == httpParserStates.COMPLETE:
                        # Invoke plugin.on_request_complete
                        for plugin in self.plugins.values():
                            upgraded_sock = plugin.on_request_complete()
                            if isinstance(upgraded_sock, ssl.SSLSocket):
                                logger.debug(
                                    'Updated client conn to %s', upgraded_sock)
                                self.client._conn = upgraded_sock
                                for plugin_ in self.plugins.values():
                                    if plugin_ != plugin:
                                        plugin_.client._conn = upgraded_sock
                            elif isinstance(upgraded_sock, bool) and upgraded_sock is True:
                                return True
            except ProtocolException as e:
                logger.exception(
                    'ProtocolException type raised', exc_info=e)
                response = e.response(self.request)
                if response:
                    self.client.queue(response)
                return True
        return False

    @contextlib.contextmanager
    def selected_events(self) -> \
            Generator[Tuple[List[Union[int, _HasFileno]],
                            List[Union[int, _HasFileno]]],
                      None, None]:
        events = self.get_events()
        for fd in events:
            self.selector.register(fd, events[fd])
        ev = self.selector.select(timeout=1)
        readables = []
        writables = []
        for key, mask in ev:
            if mask & selectors.EVENT_READ:
                readables.append(key.fileobj)
            if mask & selectors.EVENT_WRITE:
                writables.append(key.fileobj)
        yield (readables, writables)
        for fd in events.keys():
            self.selector.unregister(fd)

    def run_once(self) -> bool:
        with self.selected_events() as (readables, writables):
            teardown = self.handle_events(readables, writables)
            if teardown:
                return True
            return False

    def run(self) -> None:
        try:
            self.initialize()
            while True:
                # Teardown if client buffer is empty and connection is inactive
                if self.is_inactive():
                    logger.debug(
                        'Client buffer is empty and maximum inactivity has reached '
                        'between client and server connection, tearing down...')
                    break
                teardown = self.run_once()
                if teardown:
                    break
        except KeyboardInterrupt:  # pragma: no cover
            pass
        except ssl.SSLError as e:
            logger.exception('ssl.SSLError', exc_info=e)
        except Exception as e:
            logger.exception(
                'Exception while handling connection %r' %
                self.client.connection, exc_info=e)
        finally:
            self.shutdown()


class DevtoolsProtocolPlugin(ProtocolHandlerPlugin):
    """
    DevtoolsProtocolPlugin taps into core `ProtocolHandler`
    events and converts them into Devtools Protocol json messages.

    A DevtoolsProtocolPlugin instance is created per request.
    Per request devtool events are queued into a global multiprocessing queue.
    """

    frame_id = secrets.token_hex(8)
    loader_id = secrets.token_hex(8)

    def __init__(
            self,
            config: ProtocolConfig,
            client: TcpClientConnection,
            request: HttpParser):
        self.id: str = f'{ os.getpid() }-{ threading.get_ident() }-{ time.time() }'
        self.response = HttpParser(httpParserTypes.RESPONSE_PARSER)
        super().__init__(config, client, request)

    def get_descriptors(self) -> Tuple[List[socket.socket], List[socket.socket]]:
        return [], []

    def write_to_descriptors(self, w: List[Union[int, _HasFileno]]) -> bool:
        return False

    def read_from_descriptors(self, r: List[Union[int, _HasFileno]]) -> bool:
        return False

    def on_client_data(self, raw: bytes) -> Optional[bytes]:
        return raw

    def on_request_complete(self) -> Union[socket.socket, bool]:
        if not self.request.has_upstream_server() and \
                self.request.path == self.config.devtools_ws_path:
            return False

        # Handle devtool frontend websocket upgrade
        if self.config.devtools_event_queue:
            self.config.devtools_event_queue.put({
                'method': 'Network.requestWillBeSent',
                'params': self.request_will_be_sent(),
            })
        return False

    def on_response_chunk(self, chunk: bytes) -> bytes:
        if not self.request.has_upstream_server() and \
                self.request.path == self.config.devtools_ws_path:
            return chunk

        if self.config.devtools_event_queue:
            self.response.parse(chunk)
            if self.response.state >= httpParserStates.HEADERS_COMPLETE:
                self.config.devtools_event_queue.put({
                    'method': 'Network.responseReceived',
                    'params': self.response_received(),
                })
            if self.response.state >= httpParserStates.RCVING_BODY:
                self.config.devtools_event_queue.put({
                    'method': 'Network.dataReceived',
                    'params': self.data_received(chunk)
                })
            if self.response.state == httpParserStates.COMPLETE:
                self.config.devtools_event_queue.put({
                    'method': 'Network.loadingFinished',
                    'params': self.loading_finished()
                })
        return chunk

    def on_client_connection_close(self) -> None:
        pass

    def request_will_be_sent(self) -> Dict[str, Any]:
        now = time.time()
        return {
            'requestId': self.id,
            'loaderId': self.loader_id,
            'documentURL': 'http://proxy-py',
            'request': {
                'url': text_(
                    self.request.path
                    if self.request.has_upstream_server() else
                    b'http://' + bytes_(str(self.config.hostname)) +
                    COLON + bytes_(self.config.port) + self.request.path
                ),
                'urlFragment': '',
                'method': text_(self.request.method),
                'headers': {text_(v[0]): text_(v[1]) for v in self.request.headers.values()},
                'initialPriority': 'High',
                'mixedContentType': 'none',
                'postData': None if self.request.method != 'POST'
                else text_(self.request.body)
            },
            'timestamp': now - PROXY_PY_START_TIME,
            'wallTime': now,
            'initiator': {
                'type': 'other'
            },
            'type': text_(self.request.header(b'content-type'))
            if self.request.has_header(b'content-type')
            else 'Other',
            'frameId': self.frame_id,
            'hasUserGesture': False
        }

    def response_received(self) -> Dict[str, Any]:
        return {
            'requestId': self.id,
            'frameId': self.frame_id,
            'loaderId': self.loader_id,
            'timestamp': time.time(),
            'type': text_(self.response.header(b'content-type'))
            if self.response.has_header(b'content-type')
            else 'Other',
            'response': {
                'url': '',
                'status': '',
                'statusText': '',
                'headers': '',
                'headersText': '',
                'mimeType': '',
                'connectionReused': True,
                'connectionId': '',
                'encodedDataLength': '',
                'fromDiskCache': False,
                'fromServiceWorker': False,
                'timing': {
                    'requestTime': '',
                    'proxyStart': -1,
                    'proxyEnd': -1,
                    'dnsStart': -1,
                    'dnsEnd': -1,
                    'connectStart': -1,
                    'connectEnd': -1,
                    'sslStart': -1,
                    'sslEnd': -1,
                    'workerStart': -1,
                    'workerReady': -1,
                    'sendStart': 0,
                    'sendEnd': 0,
                    'receiveHeadersEnd': 0,
                },
                'requestHeaders': '',
                'remoteIPAddress': '',
                'remotePort': '',
            }
        }

    def data_received(self, chunk: bytes) -> Dict[str, Any]:
        return {
            'requestId': self.id,
            'timestamp': time.time(),
            'dataLength': len(chunk),
            'encodedDataLength': len(chunk),
        }

    def loading_finished(self) -> Dict[str, Any]:
        return {
            'requestId': self.id,
            'timestamp': time.time(),
            'encodedDataLength': self.response.total_size
        }


def is_py3() -> bool:
    """Exists only to avoid mocking sys.version_info in tests."""
    return sys.version_info[0] == 3


def set_open_file_limit(soft_limit: int) -> None:
    """Configure open file description soft limit on supported OS."""
    if os.name != 'nt':  # resource module not available on Windows OS
        curr_soft_limit, curr_hard_limit = resource.getrlimit(
            resource.RLIMIT_NOFILE)
        if curr_soft_limit < soft_limit < curr_hard_limit:
            resource.setrlimit(
                resource.RLIMIT_NOFILE, (soft_limit, curr_hard_limit))
            logger.debug(
                'Open file descriptor soft limit set to %d' %
                soft_limit)


def load_plugins(plugins: bytes) -> Dict[bytes, List[type]]:
    """Accepts a comma separated list of Python modules and returns
    a list of respective Python classes."""
    p: Dict[bytes, List[type]] = {
        b'ProtocolHandlerPlugin': [],
        b'HttpProxyBasePlugin': [],
        b'HttpWebServerBasePlugin': [],
    }
    for plugin_ in plugins.split(COMMA):
        plugin = text_(plugin_.strip())
        if plugin == '':
            continue
        module_name, klass_name = plugin.rsplit(text_(DOT), 1)
        klass = getattr(
            importlib.import_module(
                __name__ if module_name == 'proxy' else module_name),
            klass_name)
        base_klass = inspect.getmro(klass)[1]
        p[bytes_(base_klass.__name__)].append(klass)
        logger.info(
            'Loaded %s %s.%s',
            'plugin' if klass.__name__ != 'HttpWebServerRouteHandler' else 'route',
            module_name,
            # HttpWebServerRouteHandler route decorator adds a special
            # staticmethod to return decorated function name
            klass.__name__ if klass.__name__ != 'HttpWebServerRouteHandler' else klass.name())
    return p


def setup_logger(
        log_file: Optional[str] = DEFAULT_LOG_FILE,
        log_level: str = DEFAULT_LOG_LEVEL,
        log_format: str = DEFAULT_LOG_FORMAT) -> None:
    ll = getattr(
        logging,
        {'D': 'DEBUG',
         'I': 'INFO',
         'W': 'WARNING',
         'E': 'ERROR',
         'C': 'CRITICAL'}[log_level.upper()[0]])
    if log_file:
        logging.basicConfig(
            filename=log_file,
            filemode='a',
            level=ll,
            format=log_format)
    else:
        logging.basicConfig(level=ll, format=log_format)


def init_parser() -> argparse.ArgumentParser:
    """Initializes and returns argument parser."""
    parser = argparse.ArgumentParser(
        description='proxy.py v%s' % __version__,
        epilog='Proxy.py not working? Report at: %s/issues/new' % __homepage__
    )
    # Argument names are ordered alphabetically.
    parser.add_argument(
        '--backlog',
        type=int,
        default=DEFAULT_BACKLOG,
        help='Default: 100. Maximum number of pending connections to proxy server')
    parser.add_argument(
        '--basic-auth',
        type=str,
        default=DEFAULT_BASIC_AUTH,
        help='Default: No authentication. Specify colon separated user:password '
             'to enable basic authentication.')
    parser.add_argument(
        '--ca-key-file',
        type=str,
        default=DEFAULT_CA_KEY_FILE,
        help='Default: None. CA key to use for signing dynamically generated '
             'HTTPS certificates.  If used, must also pass --ca-cert-file and --ca-signing-key-file'
    )
    parser.add_argument(
        '--ca-cert-dir',
        type=str,
        default=DEFAULT_CA_CERT_DIR,
        help='Default: ~/.proxy.py. Directory to store dynamically generated certificates. '
             'Also see --ca-key-file, --ca-cert-file and --ca-signing-key-file'
    )
    parser.add_argument(
        '--ca-cert-file',
        type=str,
        default=DEFAULT_CA_CERT_FILE,
        help='Default: None. Signing certificate to use for signing dynamically generated '
             'HTTPS certificates.  If used, must also pass --ca-key-file and --ca-signing-key-file'
    )
    parser.add_argument(
        '--ca-signing-key-file',
        type=str,
        default=DEFAULT_CA_SIGNING_KEY_FILE,
        help='Default: None. CA signing key to use for dynamic generation of '
             'HTTPS certificates.  If used, must also pass --ca-key-file and --ca-cert-file'
    )
    parser.add_argument(
        '--cert-file',
        type=str,
        default=DEFAULT_CERT_FILE,
        help='Default: None. Server certificate to enable end-to-end TLS encryption with clients. '
             'If used, must also pass --key-file.'
    )
    parser.add_argument(
        '--client-recvbuf-size',
        type=int,
        default=DEFAULT_CLIENT_RECVBUF_SIZE,
        help='Default: 1 MB. Maximum amount of data received from the '
             'client in a single recv() operation. Bump this '
             'value for faster uploads at the expense of '
             'increased RAM.')
    parser.add_argument(
        '--devtools-ws-path',
        type=str,
        default=DEFAULT_DEVTOOLS_WS_PATH,
        help='Default: /devtools.  Only applicable '
             'if --enable-devtools is used.'
    )
    parser.add_argument(
        '--disable-headers',
        type=str,
        default=COMMA.join(DEFAULT_DISABLE_HEADERS),
        help='Default: None.  Comma separated list of headers to remove before '
             'dispatching client request to upstream server.')
    parser.add_argument(
        '--disable-http-proxy',
        action='store_true',
        default=DEFAULT_DISABLE_HTTP_PROXY,
        help='Default: False.  Whether to disable proxy.HttpProxyPlugin.')
    parser.add_argument(
        '--enable-devtools',
        action='store_true',
        default=DEFAULT_ENABLE_DEVTOOLS,
        help='Default: False.  Enables integration with Chrome Devtool Frontend.'
    )
    parser.add_argument(
        '--enable-static-server',
        action='store_true',
        default=DEFAULT_ENABLE_STATIC_SERVER,
        help='Default: False.  Enable inbuilt static file server. '
             'Optionally, also use --static-server-dir to serve static content '
             'from custom directory.  By default, static file server serves '
             'from public folder.'
    )
    parser.add_argument(
        '--enable-web-server',
        action='store_true',
        default=DEFAULT_ENABLE_WEB_SERVER,
        help='Default: False.  Whether to enable proxy.HttpWebServerPlugin.')
    parser.add_argument('--hostname',
                        type=str,
                        default=str(DEFAULT_IPV6_HOSTNAME),
                        help='Default: ::1. Server IP address.')
    parser.add_argument(
        '--key-file',
        type=str,
        default=DEFAULT_KEY_FILE,
        help='Default: None. Server key file to enable end-to-end TLS encryption with clients. '
             'If used, must also pass --cert-file.'
    )
    parser.add_argument(
        '--log-level',
        type=str,
        default=DEFAULT_LOG_LEVEL,
        help='Valid options: DEBUG, INFO (default), WARNING, ERROR, CRITICAL. '
             'Both upper and lowercase values are allowed. '
             'You may also simply use the leading character e.g. --log-level d')
    parser.add_argument('--log-file', type=str, default=DEFAULT_LOG_FILE,
                        help='Default: sys.stdout. Log file destination.')
    parser.add_argument('--log-format', type=str, default=DEFAULT_LOG_FORMAT,
                        help='Log format for Python logger.')
    parser.add_argument('--num-workers', type=int, default=DEFAULT_NUM_WORKERS,
                        help='Defaults to number of CPU cores.')
    parser.add_argument(
        '--open-file-limit',
        type=int,
        default=DEFAULT_OPEN_FILE_LIMIT,
        help='Default: 1024. Maximum number of files (TCP connections) '
             'that proxy.py can open concurrently.')
    parser.add_argument(
        '--pac-file',
        type=str,
        default=DEFAULT_PAC_FILE,
        help='A file (Proxy Auto Configuration) or string to serve when '
             'the server receives a direct file request. '
             'Using this option enables proxy.HttpWebServerPlugin.')
    parser.add_argument(
        '--pac-file-url-path',
        type=str,
        default=text_(DEFAULT_PAC_FILE_URL_PATH),
        help='Default: %s. Web server path to serve the PAC file.' %
             text_(DEFAULT_PAC_FILE_URL_PATH))
    parser.add_argument(
        '--pid-file',
        type=str,
        default=DEFAULT_PID_FILE,
        help='Default: None. Save parent process ID to a file.')
    parser.add_argument(
        '--plugins',
        type=str,
        default=DEFAULT_PLUGINS,
        help='Comma separated plugins')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT,
                        help='Default: 8899. Server port.')
    parser.add_argument(
        '--server-recvbuf-size',
        type=int,
        default=DEFAULT_SERVER_RECVBUF_SIZE,
        help='Default: 1 MB. Maximum amount of data received from the '
             'server in a single recv() operation. Bump this '
             'value for faster downloads at the expense of '
             'increased RAM.')
    parser.add_argument(
        '--static-server-dir',
        type=str,
        default=DEFAULT_STATIC_SERVER_DIR,
        help='Default: "public" folder in directory where proxy.py is placed. '
             'This option is only applicable when static server is also enabled. '
             'See --enable-static-server.'
    )
    parser.add_argument(
        '--threadless',
        action='store_true',
        default=DEFAULT_THREADLESS,
        help='Default: False.  When disabled a new thread is spawned '
             'to handle each client connection.'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=DEFAULT_TIMEOUT,
        help='Default: ' + str(DEFAULT_TIMEOUT) + '.  Number of seconds after which '
             'an inactive connection must be dropped.  Inactivity is defined by no '
             'data sent or received by the client.'
    )
    parser.add_argument(
        '--version',
        '-v',
        action='store_true',
        default=DEFAULT_VERSION,
        help='Prints proxy.py version.')
    return parser


def main(input_args: List[str]) -> None:
    if not is_py3() and not UNDER_TEST:
        print(
            'DEPRECATION: "develop" branch no longer supports Python 2.7.  Kindly upgrade to Python 3+. '
            'If for some reasons you cannot upgrade, consider using "master" branch or simply '
            '"pip install proxy.py".'
            '\n\n'
            'DEPRECATION: Python 2.7 will reach the end of its life on January 1st, 2020. '
            'Please upgrade your Python as Python 2.7 won\'t be maintained after that date. '
            'A future version of pip will drop support for Python 2.7.')
        sys.exit(0)

    args = init_parser().parse_args(input_args)

    if args.version:
        print(text_(version))
        sys.exit(0)

    if (args.cert_file and args.key_file) and \
            (args.ca_key_file and args.ca_cert_file and args.ca_signing_key_file):
        print('You can either enable end-to-end encryption OR TLS interception,'
              'not both together.')
        sys.exit(0)

    try:
        setup_logger(args.log_file, args.log_level, args.log_format)
        set_open_file_limit(args.open_file_limit)

        auth_code = None
        if args.basic_auth:
            auth_code = b'Basic %s' % base64.b64encode(bytes_(args.basic_auth))

        default_plugins = ''
        devtools_event_queue: Optional[DevtoolsEventQueueType] = None
        if args.enable_devtools:
            default_plugins += 'proxy.DevtoolsProtocolPlugin,'
            default_plugins += 'proxy.HttpWebServerPlugin,'
        if not args.disable_http_proxy:
            default_plugins += 'proxy.HttpProxyPlugin,'
        if args.enable_web_server or \
                args.pac_file is not None or \
                args.enable_static_server:
            if 'proxy.HttpWebServerPlugin' not in default_plugins:
                default_plugins += 'proxy.HttpWebServerPlugin,'
        if args.enable_devtools:
            default_plugins += 'proxy.DevtoolsWebsocketPlugin,'
            devtools_event_queue = multiprocessing.Manager().Queue()
        if args.pac_file is not None:
            default_plugins += 'proxy.HttpWebServerPacFilePlugin,'

        config = ProtocolConfig(
            auth_code=auth_code,
            server_recvbuf_size=args.server_recvbuf_size,
            client_recvbuf_size=args.client_recvbuf_size,
            pac_file=bytes_(args.pac_file),
            pac_file_url_path=bytes_(args.pac_file_url_path),
            disable_headers=[
                header.lower() for header in bytes_(
                    args.disable_headers).split(COMMA) if header.strip() != b''],
            certfile=args.cert_file,
            keyfile=args.key_file,
            ca_cert_dir=args.ca_cert_dir,
            ca_key_file=args.ca_key_file,
            ca_cert_file=args.ca_cert_file,
            ca_signing_key_file=args.ca_signing_key_file,
            hostname=ipaddress.ip_address(args.hostname),
            port=args.port,
            backlog=args.backlog,
            num_workers=args.num_workers if args.num_workers > 0 else multiprocessing.cpu_count(),
            static_server_dir=args.static_server_dir,
            enable_static_server=args.enable_static_server,
            devtools_event_queue=devtools_event_queue,
            devtools_ws_path=args.devtools_ws_path,
            timeout=args.timeout,
            threadless=args.threadless)

        config.plugins = load_plugins(
            bytes_(
                '%s%s' %
                (default_plugins, args.plugins)))

        acceptor_pool = AcceptorPool(
            hostname=config.hostname,
            port=config.port,
            backlog=config.backlog,
            num_workers=config.num_workers,
            threadless=config.threadless,
            work_klass=ProtocolHandler,
            config=config)
        if args.pid_file:
            with open(args.pid_file, 'wb') as pid_file:
                pid_file.write(bytes_(os.getpid()))
        acceptor_pool.setup()

        try:
            # TODO: Introduce cron feature instead of mindless sleep
            while True:
                time.sleep(1)
        except Exception as e:
            logger.exception('exception', exc_info=e)
        finally:
            acceptor_pool.shutdown()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        if args.pid_file:
            if os.path.exists(args.pid_file):
                os.remove(args.pid_file)


if __name__ == '__main__':
    main(sys.argv[1:])  # pragma: no cover

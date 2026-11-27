"""Small SNMP v1/v2c client (GET and GETNEXT walk) built on the stdlib.

RouterOS speaks plain SNMPv2c over UDP, so a compact BER implementation
avoids the heavyweight/version-sensitive third-party SNMP stacks and keeps
installation on Windows dependency-free.
"""

from __future__ import annotations

import random
import socket
import threading
import time

# --- OID / TLV helpers -------------------------------------------------------

GET_REQUEST = 0xA0
GET_RESPONSE = 0xA2
GET_NEXT_REQUEST = 0xA1
GET_BULK_REQUEST = 0xA5

NO_SUCH_OBJECT = 0x80
NO_SUCH_INSTANCE = 0x81
END_OF_MIB_VIEW = 0x82

ERROR_NAMES = {
    1: "tooBig",
    2: "noSuchName",
    3: "badValue",
    4: "readOnly",
    5: "genErr",
}


class SnmpError(Exception):
    """Base class for SNMP failures."""


class SnmpTimeout(SnmpError):
    """The agent did not answer in time."""


class SnmpResponseError(SnmpError):
    """The agent answered with a non-zero error-status."""


def _encode_length(length: int) -> bytes:
    if length < 0x80:
        return bytes((length,))
    encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes((0x80 | len(encoded),)) + encoded


def _tlv(tag: int, payload: bytes) -> bytes:
    return bytes((tag,)) + _encode_length(len(payload)) + payload


def _encode_int(value: int) -> bytes:
    if value == 0:
        return _tlv(0x02, b"\x00")
    size = (value.bit_length() + 8) // 8
    return _tlv(0x02, value.to_bytes(size, "big", signed=True))


def _encode_oid(dotted: str) -> bytes:
    parts = [int(part) for part in dotted.strip(".").split(".")]
    if len(parts) < 2 or not 0 <= parts[0] <= 2:
        raise ValueError(f"invalid OID: {dotted!r}")
    body = bytearray((parts[0] * 40 + parts[1],))
    for part in parts[2:]:
        if part < 0:
            raise ValueError(f"invalid OID: {dotted!r}")
        chunk = [part & 0x7F]
        part >>= 7
        while part:
            chunk.append(0x80 | (part & 0x7F))
            part >>= 7
        body.extend(reversed(chunk))
    return _tlv(0x06, bytes(body))


def _decode_oid(raw: bytes) -> str:
    if not raw:
        return ""
    first = raw[0]
    parts = [first // 40, first % 40]
    value = 0
    for byte in raw[1:]:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(value)
            value = 0
    return ".".join(str(part) for part in parts)


def _read_tlv(data: bytes, pos: int) -> tuple[int, bytes, int]:
    if pos + 2 > len(data):
        raise SnmpError("malformed SNMP response (truncated header)")
    tag = data[pos]
    length = data[pos + 1]
    pos += 2
    if length & 0x80:
        count = length & 0x7F
        if count == 0 or pos + count > len(data):
            raise SnmpError("malformed SNMP response (bad length)")
        length = int.from_bytes(data[pos:pos + count], "big")
        pos += count
    end = pos + length
    if end > len(data):
        raise SnmpError("malformed SNMP response (truncated value)")
    return tag, data[pos:end], end


def _as_int(raw: bytes, signed: bool = True) -> int:
    return int.from_bytes(raw, "big", signed=signed)


def _decode_value(tag: int, raw: bytes):
    if tag == 0x02:  # INTEGER
        return _as_int(raw)
    if tag == 0x04:  # OCTET STRING
        return raw.decode("utf-8", "replace")
    if tag == 0x06:  # OBJECT IDENTIFIER
        return _decode_oid(raw)
    if tag == 0x05:  # NULL
        return None
    if tag == 0x40:  # IpAddress
        return ".".join(str(byte) for byte in raw)
    if tag in (0x41, 0x42, 0x43, 0x46):  # Counter32, Gauge32, TimeTicks, Counter64
        return _as_int(raw, signed=False)
    if tag in (NO_SUCH_OBJECT, NO_SUCH_INSTANCE, END_OF_MIB_VIEW):
        return None
    return raw


class SnmpClient:
    """Blocking SNMPv2c client. One instance per polling thread."""

    def __init__(self, host: str, community: str = "public", port: int = 161,
                 timeout: float = 1.0, retries: int = 1, version: int = 2):
        self.host = host
        self.community = community
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self.version = 0 if version == 1 else 1
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()

    # -- transport ---------------------------------------------------------
    def _socket(self) -> socket.socket:
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.settimeout(self.timeout)
        return self._sock

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def _request(self, pdu_tag: int, oids: list[str],
                 max_repetitions: int = 0) -> list[tuple[str, object]]:
        if not oids:
            return []
        request_id = random.randint(1, 0x7FFFFFFF)
        varbinds = b"".join(
            _tlv(0x30, _encode_oid(oid) + _tlv(0x05, b"")) for oid in oids
        )
        # The third PDU field is error-index for GET/GETNEXT but
        # max-repetitions for GETBULK.
        pdu = _tlv(
            pdu_tag,
            _encode_int(request_id)
            + _encode_int(0)
            + _encode_int(max_repetitions)
            + _tlv(0x30, varbinds),
        )
        packet = _tlv(
            0x30,
            _encode_int(self.version) + _tlv(0x04, self.community.encode("utf-8")) + pdu,
        )

        with self._lock:
            sock = self._socket()
            last_error: Exception | None = None
            for _ in range(self.retries + 1):
                try:
                    sock.sendto(packet, (self.host, self.port))
                except OSError as exc:
                    last_error = exc
                    self.close()
                    sock = self._socket()
                    continue

                deadline = time.monotonic() + self.timeout
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        last_error = SnmpTimeout(
                            f"no SNMP response from {self.host}:{self.port}"
                        )
                        break
                    sock.settimeout(remaining)
                    try:
                        data, _addr = sock.recvfrom(65535)
                    except socket.timeout:
                        last_error = SnmpTimeout(
                            f"no SNMP response from {self.host}:{self.port}"
                        )
                        break
                    except ConnectionResetError:
                        # Windows reports ICMP port-unreachable as WSAECONNRESET.
                        last_error = SnmpTimeout(
                            f"no SNMP response from {self.host}:{self.port}"
                        )
                        break
                    except OSError as exc:
                        last_error = exc
                        break
                    try:
                        response_id, error_status, error_index, values = self._parse(data)
                    except SnmpError:
                        continue  # stray or malformed datagram: keep waiting
                    if response_id != request_id:
                        continue
                    if error_status:
                        name = ERROR_NAMES.get(error_status, str(error_status))
                        raise SnmpResponseError(
                            f"SNMP error {name} (status {error_status}, "
                            f"index {error_index})"
                        )
                    return values
                if not isinstance(last_error, SnmpTimeout):
                    self.close()
                    sock = self._socket()
            raise last_error or SnmpTimeout(f"no SNMP response from {self.host}")

    # -- decoding ----------------------------------------------------------
    @staticmethod
    def _parse(data: bytes) -> tuple[int, int, int, list[tuple[str, object]]]:
        tag, message, _ = _read_tlv(data, 0)
        if tag != 0x30:
            raise SnmpError("unexpected SNMP message tag")
        pos = 0
        _tag, _version, pos = _read_tlv(message, pos)
        _tag, _community, pos = _read_tlv(message, pos)
        tag, pdu, pos = _read_tlv(message, pos)
        if tag not in (GET_RESPONSE, 0xA8):  # 0xA8 = SNMPv2 report
            raise SnmpError("unexpected SNMP PDU type")
        offset = 0
        _tag, raw_id, offset = _read_tlv(pdu, offset)
        _tag, raw_status, offset = _read_tlv(pdu, offset)
        _tag, raw_index, offset = _read_tlv(pdu, offset)
        _tag, varbind_list, offset = _read_tlv(pdu, offset)

        values: list[tuple[str, object]] = []
        cursor = 0
        while cursor < len(varbind_list):
            _tag, varbind, cursor = _read_tlv(varbind_list, cursor)
            inner = 0
            _tag, raw_oid, inner = _read_tlv(varbind, inner)
            value_tag, raw_value, inner = _read_tlv(varbind, inner)
            values.append((_decode_oid(raw_oid), _decode_value(value_tag, raw_value)))
        return _as_int(raw_id), _as_int(raw_status), _as_int(raw_index), values

    # -- public API --------------------------------------------------------
    def get(self, oids: list[str]) -> dict[str, object]:
        """Fetch several OIDs in one request. Missing values map to None."""
        values = self._request(GET_REQUEST, oids)
        result: dict[str, object] = {oid: None for oid in oids}
        for oid, value in values:
            result[oid] = value
        return result

    def walk(self, root: str, max_rows: int = 2048) -> dict[str, object]:
        """Walk a subtree, keyed by full OID.

        SNMPv2c uses GETBULK (many rows per request); SNMPv1 falls back to
        GETNEXT. An agent that rejects GETBULK is retried with GETNEXT.
        """
        if self.version == 1:
            try:
                return self._walk_bulk(root, max_rows)
            except SnmpResponseError:
                pass
        return self._walk_next(root, max_rows)

    def _walk_next(self, root: str, max_rows: int) -> dict[str, object]:
        prefix = root.rstrip(".") + "."
        result: dict[str, object] = {}
        current = prefix[:-1]
        while len(result) < max_rows:
            values = self._request(GET_NEXT_REQUEST, [current])
            if not values:
                break
            oid, value = values[0]
            if value is None or not oid.startswith(prefix):
                break
            if oid == current:
                break
            result[oid] = value
            current = oid
        return result

    def _walk_bulk(self, root: str, max_rows: int,
                   repetitions: int = 25) -> dict[str, object]:
        prefix = root.rstrip(".") + "."
        result: dict[str, object] = {}
        current = prefix[:-1]
        while len(result) < max_rows:
            values = self._request(GET_BULK_REQUEST, [current], repetitions)
            if not values:
                break
            advanced = False
            for oid, value in values:
                if value is None or not oid.startswith(prefix) or oid == current:
                    return result
                result[oid] = value
                current = oid
                advanced = True
                if len(result) >= max_rows:
                    break
            if not advanced:
                break
        return result

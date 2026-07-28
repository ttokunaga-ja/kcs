import hashlib
import io
import unittest

from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_bounded_body as bounded


class _NeverRead:
    def __init__(self):
        self.called = False

    def read(self, _size):
        self.called = True
        raise AssertionError("body must not be read")


class _OversizeReader:
    def read(self, size):
        return b"x" * (size + 1)


class _ChunkedReader:
    def __init__(self, value, chunk_size):
        self.value = value
        self.chunk_size = chunk_size

    def read(self, size):
        take = min(size, self.chunk_size, len(self.value))
        result = self.value[:take]
        self.value = self.value[take:]
        return result


class _OneByteReader:
    def __init__(self, value):
        self.value = value
        self.offset = 0
        self.read_calls = 0

    def read(self, size):
        self.read_calls += 1
        if size <= 0 or self.offset == len(self.value):
            return b""
        result = self.value[self.offset : self.offset + 1]
        self.offset += 1
        return result


class PersonaV2BoundedBodyTests(unittest.TestCase):
    def setUp(self):
        self.value = {
            "artifact_schema": "kio.persona.test/v2",
            "authority": {"g0_contract_frozen": False},
            "count": 3,
        }
        self.body = artifact_common.canonical_json_bytes(
            self.value,
            label="test body",
            max_bytes=4_096,
        )
        self.digest = hashlib.sha256(self.body).hexdigest()

    def load(self, body=None, *, declared=None, digest=None, cap=4_096):
        if body is None:
            body = self.body
        if declared is None:
            declared = len(body)
        if digest is None:
            digest = hashlib.sha256(body).hexdigest()
        return bounded.load_declared_canonical_object(
            io.BytesIO(body),
            declared_body_bytes=declared,
            max_body_bytes=cap,
            expected_sha256=digest,
            label="test body",
        )

    def test_exact_chunked_body_is_detached_and_next_frame_is_not_consumed(self):
        reader = io.BytesIO(self.body + b"next-frame")
        value = bounded.load_declared_canonical_object(
            reader,
            declared_body_bytes=len(self.body),
            max_body_bytes=4_096,
            expected_sha256=self.digest,
            label="test body",
        )
        self.assertEqual(value, self.value)
        self.assertIsNot(value, self.value)
        self.assertEqual(reader.read(), b"next-frame")

        chunked = _ChunkedReader(self.body, 3)
        self.assertEqual(
            bounded.load_declared_canonical_object(
                chunked,
                declared_body_bytes=len(self.body),
                max_body_bytes=4_096,
                expected_sha256=self.digest,
                label="chunked body",
            ),
            self.value,
        )

    def test_over_cap_length_is_rejected_before_first_read(self):
        reader = _NeverRead()
        with self.assertRaises(bounded.PersonaV2BoundedBodyError):
            bounded.read_declared_body(
                reader,
                declared_body_bytes=101,
                max_body_bytes=100,
                label="over cap",
            )
        self.assertFalse(reader.called)

        reader = _NeverRead()
        with self.assertRaises(bounded.PersonaV2BoundedBodyError):
            bounded.read_declared_body(
                reader,
                declared_body_bytes=bounded.MAX_SUPPORTED_BODY_BYTES + 1,
                max_body_bytes=bounded.MAX_SUPPORTED_BODY_BYTES,
                label="global over cap",
            )
        self.assertFalse(reader.called)

    def test_one_byte_short_reads_use_the_same_declared_boundary(self):
        body = bytes(range(256)) * 16
        reader = _OneByteReader(body + b"next-frame")
        self.assertEqual(
            bounded.read_declared_body(
                reader,
                declared_body_bytes=len(body),
                max_body_bytes=len(body),
                label="one-byte reader",
            ),
            body,
        )
        self.assertEqual(reader.read_calls, len(body))
        self.assertEqual(reader.value[reader.offset :], b"next-frame")

    def test_length_reader_and_digest_fail_closed(self):
        with self.assertRaises(bounded.PersonaV2BoundedBodyError):
            bounded.read_declared_body(
                io.BytesIO(self.body[:-1]),
                declared_body_bytes=len(self.body),
                max_body_bytes=4_096,
                label="short body",
            )
        with self.assertRaises(bounded.PersonaV2BoundedBodyError):
            bounded.read_declared_body(
                _OversizeReader(),
                declared_body_bytes=10,
                max_body_bytes=10,
                label="lying reader",
            )
        with self.assertRaises(bounded.PersonaV2BoundedBodyError):
            bounded.read_declared_body(
                object(),
                declared_body_bytes=10,
                max_body_bytes=10,
                label="missing reader",
            )
        with self.assertRaises(bounded.PersonaV2BoundedBodyError):
            self.load(digest="0" * 64)
        for invalid in (True, 0, -1, bounded.MAX_SUPPORTED_BODY_BYTES + 1):
            with self.subTest(invalid=invalid):
                with self.assertRaises(bounded.PersonaV2BoundedBodyError):
                    bounded.read_declared_body(
                        io.BytesIO(self.body),
                        declared_body_bytes=invalid,
                        max_body_bytes=4_096,
                        label="invalid length",
                    )

    def test_noncanonical_or_non_plain_json_is_rejected(self):
        cases = (
            b'{"b":1,"a":2}',
            b'{"a":1, "b":2}',
            b'{"a":1,"a":1}',
            b'{"a":1.0}',
            b'{"a":-1}',
            b'{"a":null}',
            b'[]',
            b'{"a":"e\\u0301"}',
            b'{"a":NaN}',
            b'\xff',
        )
        for body in cases:
            with self.subTest(body=body):
                with self.assertRaises(bounded.PersonaV2BoundedBodyError):
                    self.load(body)

    def test_exact_type_and_global_cap_validation(self):
        reader = _NeverRead()
        with self.assertRaises(bounded.PersonaV2BoundedBodyError):
            bounded.load_declared_canonical_object(
                reader,
                declared_body_bytes=len(self.body),
                max_body_bytes=4_096,
                expected_sha256=None,
                label="invalid digest",
            )
        self.assertFalse(reader.called)
        invalid_digests = (True, "A" * 64, "0" * 63, "z" * 64)
        for digest in invalid_digests:
            with self.subTest(digest=digest):
                with self.assertRaises(bounded.PersonaV2BoundedBodyError):
                    self.load(digest=digest)
        for cap in (True, 0, -1, bounded.MAX_SUPPORTED_BODY_BYTES + 1):
            with self.subTest(cap=cap):
                with self.assertRaises(bounded.PersonaV2BoundedBodyError):
                    bounded.read_declared_body(
                        _NeverRead(),
                        declared_body_bytes=1,
                        max_body_bytes=cap,
                        label="invalid cap",
                    )


if __name__ == "__main__":
    unittest.main()

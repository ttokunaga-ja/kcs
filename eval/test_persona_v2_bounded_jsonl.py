import hashlib
import io
import json
import unittest

from eval import persona_v2_bounded_jsonl as bounded_jsonl


def _canonical_row(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"


def _descriptor(body, keys):
    return {
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "first_key": keys[0],
        "last_key": keys[-1],
        "row_count": len(keys),
    }


class _NeverRead:
    def __init__(self):
        self.called = False

    def read(self, _size):
        self.called = True
        raise AssertionError("invalid envelope must be rejected before reading")


class _ChunkedReader:
    def __init__(self, value, chunk_size):
        self.value = value
        self.chunk_size = chunk_size

    def read(self, size):
        take = min(size, self.chunk_size, len(self.value))
        result = self.value[:take]
        self.value = self.value[take:]
        return result


class _OversizeReader:
    def read(self, size):
        return b"x" * (size + 1)


class PersonaV2BoundedJsonlTests(unittest.TestCase):
    def setUp(self):
        self.values = (
            {"count": 0, "intent_key": "p01-a", "nested": {"ok": True}},
            {"count": 1, "intent_key": "p01-b", "text": "日本語"},
            {"count": 2, "intent_key": "p01-c", "values": [1, 2]},
        )
        self.body = b"".join(_canonical_row(value) for value in self.values)
        self.descriptor = _descriptor(
            self.body,
            [value["intent_key"] for value in self.values],
        )

    def load(self, body=None, *, descriptor=None, declared=None, **overrides):
        if body is None:
            body = self.body
        if descriptor is None:
            descriptor = _descriptor(
                body,
                [value["intent_key"] for value in self.values],
            )
        if declared is None:
            declared = len(body)
        arguments = {
            "declared_body_bytes": declared,
            "descriptor": descriptor,
            "key_field": "intent_key",
            "max_body_bytes": 4_096,
            "max_row_bytes_including_lf": 256,
            "max_rows": 16,
        }
        arguments.update(overrides)
        return bounded_jsonl.load_declared_canonical_jsonl(
            io.BytesIO(body),
            **arguments,
        )

    def test_chunked_load_is_detached_and_does_not_consume_next_frame(self):
        reader = io.BytesIO(self.body + b"next-frame")
        loaded = bounded_jsonl.load_declared_canonical_jsonl(
            reader,
            declared_body_bytes=len(self.body),
            descriptor=self.descriptor,
            key_field="intent_key",
            max_body_bytes=4_096,
            max_row_bytes_including_lf=256,
            max_rows=16,
        )
        self.assertEqual(loaded, self.values)
        self.assertIsNot(loaded[0], self.values[0])
        self.assertEqual(reader.read(), b"next-frame")

        chunked = _ChunkedReader(self.body, 2)
        self.assertEqual(
            bounded_jsonl.load_declared_canonical_jsonl(
                chunked,
                declared_body_bytes=len(self.body),
                descriptor=self.descriptor,
                key_field="intent_key",
                max_body_bytes=4_096,
                max_row_bytes_including_lf=256,
                max_rows=16,
            ),
            self.values,
        )

    def test_all_caps_and_descriptor_are_validated_before_first_read(self):
        invalid_argument_sets = (
            {"declared_body_bytes": 101, "max_body_bytes": 100},
            {
                "declared_body_bytes": bounded_jsonl.HARD_MAX_BODY_BYTES + 1,
                "max_body_bytes": bounded_jsonl.HARD_MAX_BODY_BYTES,
            },
            {"max_body_bytes": True},
            {"max_body_bytes": bounded_jsonl.HARD_MAX_BODY_BYTES + 1},
            {"max_row_bytes_including_lf": True},
            {
                "max_row_bytes_including_lf": (
                    bounded_jsonl.HARD_MAX_ROW_BYTES_INCLUDING_LF + 1
                )
            },
            {"max_rows": True},
            {"max_rows": bounded_jsonl.HARD_MAX_ROWS + 1},
            {"key_field": ""},
        )
        base = {
            "declared_body_bytes": len(self.body),
            "descriptor": self.descriptor,
            "key_field": "intent_key",
            "max_body_bytes": 4_096,
            "max_row_bytes_including_lf": 256,
            "max_rows": 16,
        }
        for overrides in invalid_argument_sets:
            with self.subTest(overrides=overrides):
                reader = _NeverRead()
                arguments = dict(base)
                arguments.update(overrides)
                with self.assertRaises(bounded_jsonl.PersonaV2BoundedJsonlError):
                    bounded_jsonl.load_declared_canonical_jsonl(reader, **arguments)
                self.assertFalse(reader.called)

        bad_descriptor = dict(self.descriptor, row_count=17)
        reader = _NeverRead()
        with self.assertRaises(bounded_jsonl.PersonaV2BoundedJsonlError):
            bounded_jsonl.load_declared_canonical_jsonl(
                reader,
                declared_body_bytes=len(self.body),
                descriptor=bad_descriptor,
                key_field="intent_key",
                max_body_bytes=4_096,
                max_row_bytes_including_lf=256,
                max_rows=16,
            )
        self.assertFalse(reader.called)

    def test_exact_length_reader_and_lf_inclusive_row_bound_fail_closed(self):
        with self.assertRaises(bounded_jsonl.PersonaV2BoundedJsonlError):
            bounded_jsonl.load_declared_canonical_jsonl(
                io.BytesIO(self.body[:-1]),
                declared_body_bytes=len(self.body),
                descriptor=self.descriptor,
                key_field="intent_key",
                max_body_bytes=4_096,
                max_row_bytes_including_lf=256,
                max_rows=16,
            )
        with self.assertRaises(bounded_jsonl.PersonaV2BoundedJsonlError):
            bounded_jsonl.load_declared_canonical_jsonl(
                _OversizeReader(),
                declared_body_bytes=10,
                descriptor={
                    "body_sha256": "0" * 64,
                    "first_key": "a",
                    "last_key": "a",
                    "row_count": 1,
                },
                key_field="intent_key",
                max_body_bytes=10,
                max_row_bytes_including_lf=10,
                max_rows=1,
            )

        first = _canonical_row(self.values[0])
        descriptor = _descriptor(first, ["p01-a"])
        self.assertEqual(
            len(first),
            len(first[:-1]) + 1,
        )
        loaded = bounded_jsonl.load_declared_canonical_jsonl(
            io.BytesIO(first),
            declared_body_bytes=len(first),
            descriptor=descriptor,
            key_field="intent_key",
            max_body_bytes=4_096,
            max_row_bytes_including_lf=len(first),
            max_rows=1,
        )
        self.assertEqual(loaded, (self.values[0],))
        with self.assertRaises(bounded_jsonl.PersonaV2BoundedJsonlError):
            bounded_jsonl.load_declared_canonical_jsonl(
                io.BytesIO(first),
                declared_body_bytes=len(first),
                descriptor=descriptor,
                key_field="intent_key",
                max_body_bytes=4_096,
                max_row_bytes_including_lf=len(first) - 1,
                max_rows=1,
            )

    def test_bom_cr_blank_missing_lf_utf8_and_nfc_are_rejected(self):
        bom_body = b"\xef\xbb\xbf" + _canonical_row({"intent_key": "a"})
        cases = (
            bom_body,
            b'{"intent_key":"a"}\r\n',
            b'{"intent_key":"a"}\r',
            b'{"intent_key":"a"}\n\n',
            b'{"intent_key":"a"}',
            b'{"intent_key":"\xff"}\n',
            '{"intent_key":"e\u0301"}\n'.encode("utf-8"),
        )
        self.assertTrue(bom_body.startswith(b"\xef\xbb\xbf"))
        for body in cases:
            with self.subTest(body=body):
                descriptor = {
                    "body_sha256": hashlib.sha256(body).hexdigest(),
                    "first_key": "a",
                    "last_key": "a",
                    "row_count": 1,
                }
                with self.assertRaises(bounded_jsonl.PersonaV2BoundedJsonlError):
                    self.load(body, descriptor=descriptor)

    def test_duplicate_keys_plain_value_and_noncanonical_json_are_rejected(self):
        cases = (
            b'{"intent_key":"a","intent_key":"a"}\n',
            b'{"intent_key":"a","value":1.0}\n',
            b'{"intent_key":"a","value":null}\n',
            b'{"intent_key":"a","value":-1}\n',
            b'{"intent_key":"a","value":NaN}\n',
            b'{"value":1,"intent_key":"a"}\n',
            b'{"intent_key": "a"}\n',
            b'["a"]\n',
            b'{"value":1}\n',
            b'{"intent_key":1}\n',
        )
        for body in cases:
            with self.subTest(body=body):
                descriptor = {
                    "body_sha256": hashlib.sha256(body).hexdigest(),
                    "first_key": "a",
                    "last_key": "a",
                    "row_count": 1,
                }
                with self.assertRaises(bounded_jsonl.PersonaV2BoundedJsonlError):
                    self.load(body, descriptor=descriptor)

    def test_duplicate_or_non_strict_row_keys_are_rejected(self):
        key_sequences = (
            ("a", "a"),
            ("b", "a"),
            ("é", "z"),  # UTF-8 byte order, not locale order.
        )
        for keys in key_sequences:
            with self.subTest(keys=keys):
                body = b"".join(
                    _canonical_row({"intent_key": key, "ordinal": index})
                    for index, key in enumerate(keys)
                )
                descriptor = _descriptor(body, sorted(keys))
                # Descriptor must itself be plausible so row-order validation is hit.
                descriptor["first_key"] = min(keys, key=lambda item: item.encode())
                descriptor["last_key"] = max(keys, key=lambda item: item.encode())
                if descriptor["first_key"] == descriptor["last_key"]:
                    descriptor["last_key"] = descriptor["first_key"] + "z"
                with self.assertRaises(bounded_jsonl.PersonaV2BoundedJsonlError):
                    self.load(body, descriptor=descriptor)

    def test_descriptor_fields_count_boundaries_and_digest_are_exact(self):
        descriptors = []
        descriptors.append(dict(self.descriptor, body_sha256="0" * 64))
        descriptors.append(dict(self.descriptor, first_key="p01-z"))
        descriptors.append(dict(self.descriptor, last_key="p01-z"))
        descriptors.append(dict(self.descriptor, row_count=2))
        extra = dict(self.descriptor)
        extra["authority"] = True
        descriptors.append(extra)
        missing = dict(self.descriptor)
        del missing["last_key"]
        descriptors.append(missing)
        descriptors.append(dict(self.descriptor, body_sha256="A" * 64))
        descriptors.append(dict(self.descriptor, first_key="p01-z", last_key="p01-a"))
        for descriptor in descriptors:
            with self.subTest(descriptor=descriptor):
                with self.assertRaises(bounded_jsonl.PersonaV2BoundedJsonlError):
                    self.load(descriptor=descriptor)

        with self.assertRaises(bounded_jsonl.PersonaV2BoundedJsonlError):
            self.load(max_rows=2)


if __name__ == "__main__":
    unittest.main()

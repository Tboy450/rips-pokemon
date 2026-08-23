import base64
import unittest

from rips_ai.device import DeviceAccessError, _decode_indexed_chunks


def encoded_chunk(index: int, raw: bytes) -> str:
    encoded = base64.b64encode(raw).decode("ascii")
    return f"__RIPS_CHUNK_{index:08d}__{encoded}__END__\n"


class DeviceReadbackTests(unittest.TestCase):
    def test_decode_indexed_chunks_from_stdout_and_stderr(self):
        stdout = encoded_chunk(0, b"\x89PNG\r\n\x1a\n") + encoded_chunk(2, b"tail")
        stderr = encoded_chunk(1, b"middle")

        self.assertEqual(
            _decode_indexed_chunks(stdout, stderr, 3),
            b"\x89PNG\r\n\x1a\nmiddletail",
        )

    def test_decode_indexed_chunks_rejects_missing_chunk(self):
        with self.assertRaises(DeviceAccessError):
            _decode_indexed_chunks(encoded_chunk(0, b"first"), "", 2)


if __name__ == "__main__":
    unittest.main()

import base64
import unittest
import zlib

from rips_ai.device import DeviceAccessError, _decode_base64_chunk, _validate_png


def png_chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return len(data).to_bytes(4, "big") + kind + data + crc.to_bytes(4, "big")


def one_pixel_png() -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = (
        (1).to_bytes(4, "big")
        + (1).to_bytes(4, "big")
        + bytes([8, 6, 0, 0, 0])
    )
    idat = zlib.compress(b"\x00\x00\x00\x00\x00")
    return signature + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", idat) + png_chunk(b"IEND", b"")


class DeviceReadbackTests(unittest.TestCase):
    def test_decode_base64_chunk_from_stdout(self):
        raw = b"\x89PNG\r\n\x1a\n"
        stdout = base64.b64encode(raw).decode("ascii")

        self.assertEqual(_decode_base64_chunk(stdout, "", len(raw), 0, b"\x89PNG"), raw)

    def test_decode_base64_chunk_from_split_streams(self):
        raw = b"\x89PNG\r\n\x1a\nmiddle"
        encoded = base64.b64encode(raw).decode("ascii")

        self.assertEqual(_decode_base64_chunk(encoded[8:], encoded[:8], len(raw), 0), raw)

    def test_decode_base64_chunk_rejects_bad_data(self):
        with self.assertRaises(DeviceAccessError):
            _decode_base64_chunk("not screenshot data", "", 8, 0)

    def test_validate_png_accepts_valid_png(self):
        _validate_png(one_pixel_png())

    def test_validate_png_rejects_corrupt_png(self):
        corrupt = bytearray(one_pixel_png())
        corrupt[-5] ^= 0xFF

        with self.assertRaises(DeviceAccessError):
            _validate_png(bytes(corrupt))


if __name__ == "__main__":
    unittest.main()

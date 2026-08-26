import base64
import unittest
import zlib

from rips_ai.device import (
    DeviceAccessError,
    INDEXED_READ_CHUNK_BYTES,
    _decode_indexed_chunks,
    _decode_base64_chunk,
    _validate_png,
    describe_png_frame,
)


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


def rgba_png(width: int, height: int, rows: list[bytes]) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + bytes([8, 6, 0, 0, 0])
    )
    raw = b"".join(b"\x00" + row for row in rows)
    idat = zlib.compress(raw)
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

    def test_decode_indexed_chunks_accepts_split_streams(self):
        first = b"a" * INDEXED_READ_CHUNK_BYTES
        second = b"bc"
        stdout = "__RIPS_CHUNK__000001:" + base64.b64encode(second).decode("ascii")
        stderr = "__RIPS_CHUNK__000000:" + base64.b64encode(first).decode("ascii")

        chunks = _decode_indexed_chunks(
            stdout,
            stderr,
            len(first) + len(second),
            INDEXED_READ_CHUNK_BYTES,
        )

        self.assertEqual(chunks, {0: first, 1: second})

    def test_validate_png_accepts_valid_png(self):
        _validate_png(one_pixel_png())

    def test_validate_png_rejects_corrupt_png(self):
        corrupt = bytearray(one_pixel_png())
        corrupt[-5] ^= 0xFF

        with self.assertRaises(DeviceAccessError):
            _validate_png(bytes(corrupt))

    def test_describe_png_frame_marks_dark_flat_image_blank(self):
        frame = describe_png_frame(one_pixel_png())

        self.assertTrue(frame["supported"])
        self.assertTrue(frame["likely_blank"])
        self.assertEqual(frame["reason"], "blank dark frame")

    def test_describe_png_frame_marks_varied_image_visible(self):
        image = rgba_png(
            2,
            1,
            [
                bytes(
                    [
                        0,
                        0,
                        0,
                        255,
                        255,
                        255,
                        255,
                        255,
                    ]
                )
            ],
        )

        frame = describe_png_frame(image)

        self.assertTrue(frame["supported"])
        self.assertFalse(frame["likely_blank"])
        self.assertEqual(frame["reason"], "visible image variation")


if __name__ == "__main__":
    unittest.main()

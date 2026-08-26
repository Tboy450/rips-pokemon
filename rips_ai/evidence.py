from __future__ import annotations

import base64
import binascii
import re
import shlex
import shutil
import subprocess
import zlib
from pathlib import Path

from .android_state import DeviceAccessError

READ_CHUNK_BYTES = 32 * 1024
INDEXED_READ_CHUNK_BYTES = 1536
BASE64_CHARS_RE = re.compile(r"[A-Za-z0-9+/=]")
INDEXED_CHUNK_RE = re.compile(r"__RIPS_CHUNK__(\d+):([A-Za-z0-9+/=]*)")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_COLOR_CHANNELS = {
    0: (1, (0,)),
    2: (3, (0, 1, 2)),
    6: (4, (0, 1, 2)),
}


def _run_shizuku_text(
    shizuku: str,
    command: str,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [shizuku, "sh", "-c", command],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise DeviceAccessError("Shizuku timed out while reading the captured screenshot.") from exc


def _read_remote_file(
    shizuku: str,
    remote_path: str,
    timeout_seconds: int,
) -> bytes:
    quoted_path = shlex.quote(remote_path)
    size_result = _run_shizuku_text(shizuku, f"wc -c < {quoted_path}", timeout_seconds)
    if size_result.returncode != 0:
        message = size_result.stderr.strip() or size_result.stdout.strip()
        raise DeviceAccessError(message or f"screenshot was not readable at {remote_path}")

    size_match = re.search(r"\d+", f"{size_result.stdout}\n{size_result.stderr}")
    if size_match is None:
        raise DeviceAccessError(f"could not determine screenshot size at {remote_path}")
    expected_size = int(size_match.group(0))
    if expected_size <= 0:
        raise DeviceAccessError(f"screenshot was empty at {remote_path}")

    try:
        return _read_remote_file_indexed(
            shizuku,
            remote_path,
            expected_size,
            timeout_seconds,
        )
    except DeviceAccessError as exc:
        indexed_error = exc

    try:
        return _read_remote_file_sequential(
            shizuku,
            remote_path,
            expected_size,
            timeout_seconds,
        )
    except DeviceAccessError as sequential_error:
        raise DeviceAccessError(
            "screenshot readback failed after screencap succeeded; "
            f"indexed transfer: {indexed_error}; "
            f"sequential transfer: {sequential_error}"
        ) from sequential_error


def _read_remote_file_indexed(
    shizuku: str,
    remote_path: str,
    expected_size: int,
    timeout_seconds: int,
) -> bytes:
    quoted_path = shlex.quote(remote_path)
    chunk_size = INDEXED_READ_CHUNK_BYTES
    command = (
        f"p={quoted_path}; bs={chunk_size}; size=$(wc -c < \"$p\"); i=0; "
        "while [ $((i * bs)) -lt \"$size\" ]; do "
        "encoded=$(dd if=\"$p\" bs=\"$bs\" skip=\"$i\" count=1 2>/dev/null | base64 -w 0); "
        "printf \"__RIPS_CHUNK__%06d:%s\\n\" \"$i\" \"$encoded\"; "
        "i=$((i + 1)); "
        "done"
    )
    result = _run_shizuku_text(shizuku, command, timeout_seconds)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise DeviceAccessError(message or "indexed screenshot readback failed")

    chunks = _decode_indexed_chunks(
        result.stdout,
        result.stderr,
        expected_size,
        chunk_size,
    )
    missing = [
        index
        for index in range(_chunk_count(expected_size, chunk_size))
        if index not in chunks
    ]
    if missing:
        chunks.update(
            _read_remote_chunks(
                shizuku,
                remote_path,
                expected_size,
                chunk_size,
                missing,
                timeout_seconds,
            )
        )

    if len(chunks) != _chunk_count(expected_size, chunk_size):
        missing = [
            index + 1
            for index in range(_chunk_count(expected_size, chunk_size))
            if index not in chunks
        ]
        preview = ", ".join(str(index) for index in missing[:8])
        if len(missing) > 8:
            preview += ", ..."
        raise DeviceAccessError(f"indexed screenshot readback missed chunk(s): {preview}")

    image_bytes = b"".join(
        chunks[index] for index in range(_chunk_count(expected_size, chunk_size))
    )
    if len(image_bytes) != expected_size:
        raise DeviceAccessError(
            "indexed screenshot readback size mismatch: "
            f"expected {expected_size}, got {len(image_bytes)}"
        )
    return image_bytes


def _chunk_count(expected_size: int, chunk_size: int) -> int:
    return (expected_size + chunk_size - 1) // chunk_size


def _decode_indexed_chunks(
    stdout: str,
    stderr: str,
    expected_size: int,
    chunk_size: int,
) -> dict[int, bytes]:
    chunks: dict[int, bytes] = {}
    for text in (stdout, stderr):
        for match in INDEXED_CHUNK_RE.finditer(text):
            index = int(match.group(1))
            if index >= _chunk_count(expected_size, chunk_size):
                continue
            expected_chunk_size = min(
                chunk_size,
                expected_size - (index * chunk_size),
            )
            try:
                decoded = base64.b64decode(match.group(2), validate=True)
            except (binascii.Error, ValueError):
                continue
            if len(decoded) == expected_chunk_size:
                chunks[index] = decoded
    return chunks


def _read_remote_chunks(
    shizuku: str,
    remote_path: str,
    expected_size: int,
    chunk_size: int,
    indexes: list[int],
    timeout_seconds: int,
) -> dict[int, bytes]:
    chunks: dict[int, bytes] = {}
    quoted_path = shlex.quote(remote_path)
    for index in indexes:
        expected_chunk_size = min(
            chunk_size,
            expected_size - (index * chunk_size),
        )
        command = (
            f"dd if={quoted_path} bs={chunk_size} "
            f"skip={index} count=1 2>/dev/null | base64 -w 0"
        )
        result = _run_shizuku_text(shizuku, command, timeout_seconds)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise DeviceAccessError(message or f"could not read screenshot chunk {index + 1}")
        chunks[index] = _decode_base64_chunk(
            result.stdout,
            result.stderr,
            expected_chunk_size,
            index,
            required_prefix=PNG_SIGNATURE if index == 0 else b"",
        )
    return chunks


def _read_remote_file_sequential(
    shizuku: str,
    remote_path: str,
    expected_size: int,
    timeout_seconds: int,
) -> bytes:
    quoted_path = shlex.quote(remote_path)
    chunks: list[bytes] = []
    chunk_count = (expected_size + READ_CHUNK_BYTES - 1) // READ_CHUNK_BYTES
    for index in range(chunk_count):
        expected_chunk_size = min(
            READ_CHUNK_BYTES,
            expected_size - (index * READ_CHUNK_BYTES),
        )
        command = (
            f"dd if={quoted_path} bs={READ_CHUNK_BYTES} "
            f"skip={index} count=1 2>/dev/null | base64 | tr -d '\\n'"
        )
        result = _run_shizuku_text(shizuku, command, timeout_seconds)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise DeviceAccessError(message or f"could not read screenshot chunk {index + 1}")
        chunks.append(
            _decode_base64_chunk(
                result.stdout,
                result.stderr,
                expected_chunk_size,
                index,
                required_prefix=b"\x89PNG\r\n\x1a\n" if index == 0 else b"",
            )
        )

    image_bytes = b"".join(chunks)
    if len(image_bytes) != expected_size:
        raise DeviceAccessError(
            f"screenshot readback size mismatch: expected {expected_size}, got {len(image_bytes)}"
        )
    return image_bytes


def _decode_base64_chunk(
    stdout: str,
    stderr: str,
    expected_size: int,
    chunk_index: int,
    required_prefix: bytes = b"",
) -> bytes:
    stdout_encoded = "".join(BASE64_CHARS_RE.findall(stdout))
    stderr_encoded = "".join(BASE64_CHARS_RE.findall(stderr))
    if stdout_encoded and stderr_encoded:
        candidates = (
            stdout_encoded + stderr_encoded,
            stderr_encoded + stdout_encoded,
            stdout_encoded,
            stderr_encoded,
        )
    else:
        candidates = (stdout_encoded, stderr_encoded)

    for encoded in candidates:
        if not encoded:
            continue
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            continue
        if len(decoded) == expected_size and decoded.startswith(required_prefix):
            return decoded
    raise DeviceAccessError(f"screenshot chunk {chunk_index + 1} was not valid base64")


def capture_screenshot(
    output_path: Path,
    remote_path: str = "/sdcard/rips_ai_latest_screen.png",
    timeout_seconds: int = 20,
) -> Path:
    shizuku = shutil.which("shizuku")
    if shizuku is None:
        raise DeviceAccessError("shizuku command is not available")

    try:
        completed = subprocess.run(
            [shizuku, "screencap", "-p", remote_path],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise DeviceAccessError(
            "Shizuku timed out. Disable battery optimization for Codex and "
            "Shizuku, then confirm Shizuku service is running."
        ) from exc

    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise DeviceAccessError(message or "Shizuku screencap failed")

    image_bytes = _read_remote_file(shizuku, remote_path, timeout_seconds)
    _validate_png(image_bytes)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)
    return output_path


def describe_png_frame(image_bytes: bytes) -> dict[str, int | bool | str]:
    _validate_png(image_bytes)
    width, height, bit_depth, color_type, idat = _png_metadata_and_idat(image_bytes)
    result: dict[str, int | bool | str] = {
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "color_type": color_type,
    }
    if bit_depth != 8 or color_type not in PNG_COLOR_CHANNELS:
        result.update(
            {
                "supported": False,
                "likely_blank": False,
                "reason": "unsupported PNG pixel format",
            }
        )
        return result

    channels, color_offsets = PNG_COLOR_CHANNELS[color_type]
    row_bytes = width * channels
    try:
        decompressed = zlib.decompress(idat)
    except zlib.error:
        result.update(
            {
                "supported": False,
                "likely_blank": False,
                "reason": "PNG image data was not decompressible",
            }
        )
        return result

    expected = height * (row_bytes + 1)
    if len(decompressed) < expected:
        result.update(
            {
                "supported": False,
                "likely_blank": False,
                "reason": "PNG image data was truncated",
            }
        )
        return result

    previous = bytearray(row_bytes)
    color_min = 255
    color_max = 0
    color_sum = 0
    color_samples = 0
    offset = 0
    for _ in range(height):
        filter_type = decompressed[offset]
        offset += 1
        row = bytearray(decompressed[offset : offset + row_bytes])
        offset += row_bytes
        _unfilter_png_row(row, previous, channels, filter_type)
        for pixel in range(0, row_bytes, channels):
            for channel in color_offsets:
                value = row[pixel + channel]
                color_min = min(color_min, value)
                color_max = max(color_max, value)
                color_sum += value
                color_samples += 1
        previous = row

    color_range = color_max - color_min
    color_mean = round(color_sum / color_samples) if color_samples else 0
    likely_blank = color_range <= 2
    if likely_blank and color_max <= 8:
        reason = "blank dark frame"
    elif likely_blank:
        reason = "flat color frame"
    else:
        reason = "visible image variation"
    result.update(
        {
            "supported": True,
            "color_min": color_min,
            "color_max": color_max,
            "color_range": color_range,
            "color_mean": color_mean,
            "likely_blank": likely_blank,
            "reason": reason,
        }
    )
    return result


def _png_metadata_and_idat(image_bytes: bytes) -> tuple[int, int, int, int, bytes]:
    offset = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = None
    idat_parts: list[bytes] = []
    while offset + 12 <= len(image_bytes):
        length = int.from_bytes(image_bytes[offset : offset + 4], "big")
        chunk_type = image_bytes[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        data = image_bytes[data_start:data_end]
        if chunk_type == b"IHDR":
            width = int.from_bytes(data[0:4], "big")
            height = int.from_bytes(data[4:8], "big")
            bit_depth = data[8]
            color_type = data[9]
        elif chunk_type == b"IDAT":
            idat_parts.append(data)
        offset = data_end + 4
        if chunk_type == b"IEND":
            break

    if width is None or height is None or bit_depth is None or color_type is None:
        raise DeviceAccessError("captured screenshot PNG was missing IHDR")
    if not idat_parts:
        raise DeviceAccessError("captured screenshot PNG was missing IDAT")
    return width, height, bit_depth, color_type, b"".join(idat_parts)


def _unfilter_png_row(
    row: bytearray,
    previous: bytearray,
    bytes_per_pixel: int,
    filter_type: int,
) -> None:
    if filter_type == 0:
        return
    if filter_type == 1:
        for index, value in enumerate(row):
            left = row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            row[index] = (value + left) & 0xFF
        return
    if filter_type == 2:
        for index, value in enumerate(row):
            row[index] = (value + previous[index]) & 0xFF
        return
    if filter_type == 3:
        for index, value in enumerate(row):
            left = row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            up = previous[index]
            row[index] = (value + ((left + up) // 2)) & 0xFF
        return
    if filter_type == 4:
        for index, value in enumerate(row):
            left = row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            up = previous[index]
            up_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            row[index] = (value + _paeth_predictor(left, up, up_left)) & 0xFF
        return
    raise DeviceAccessError(f"captured screenshot PNG used invalid filter {filter_type}")


def _paeth_predictor(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    up_left_distance = abs(estimate - up_left)
    if left_distance <= up_distance and left_distance <= up_left_distance:
        return left
    if up_distance <= up_left_distance:
        return up
    return up_left


def _validate_png(image_bytes: bytes) -> None:
    if not image_bytes.startswith(PNG_SIGNATURE):
        raise DeviceAccessError("captured screenshot was not a PNG image")

    offset = len(PNG_SIGNATURE)
    while offset + 12 <= len(image_bytes):
        length = int.from_bytes(image_bytes[offset : offset + 4], "big")
        chunk_type = image_bytes[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(image_bytes):
            raise DeviceAccessError("captured screenshot PNG was truncated")

        actual_crc = int.from_bytes(image_bytes[data_end:crc_end], "big")
        expected_crc = zlib.crc32(chunk_type)
        expected_crc = zlib.crc32(image_bytes[data_start:data_end], expected_crc) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            name = chunk_type.decode("ascii", errors="replace")
            raise DeviceAccessError(f"captured screenshot PNG CRC failed in {name}")

        offset = crc_end
        if chunk_type == b"IEND":
            if offset != len(image_bytes):
                raise DeviceAccessError("captured screenshot PNG had trailing data")
            return

    raise DeviceAccessError("captured screenshot PNG was missing IEND")

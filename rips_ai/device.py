from __future__ import annotations

import base64
import binascii
import re
import shlex
import shutil
import subprocess
import zlib
from pathlib import Path

READ_CHUNK_BYTES = 16 * 1024
BASE64_CHARS_RE = re.compile(r"[A-Za-z0-9+/=]")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class DeviceAccessError(RuntimeError):
    pass


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

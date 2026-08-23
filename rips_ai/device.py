from __future__ import annotations

import base64
import binascii
import re
import shlex
import shutil
import subprocess
from pathlib import Path

READ_CHUNK_BYTES = 1024
CHUNK_RE = re.compile(r"__RIPS_CHUNK_(\d{8})__([A-Za-z0-9+/=]+)__END__")


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

    size_match = re.search(r"\d+", size_result.stdout)
    if size_match is None:
        raise DeviceAccessError(f"could not determine screenshot size at {remote_path}")
    expected_size = int(size_match.group(0))
    if expected_size <= 0:
        raise DeviceAccessError(f"screenshot was empty at {remote_path}")

    chunk_count = (expected_size + READ_CHUNK_BYTES - 1) // READ_CHUNK_BYTES
    command = f"""
i=0
while [ "$i" -lt {chunk_count} ]; do
  printf '__RIPS_CHUNK_%08d__' "$i"
  dd if={quoted_path} bs={READ_CHUNK_BYTES} skip="$i" count=1 2>/dev/null | base64 | tr -d '\\n'
  printf '__END__\\n'
  i=$((i + 1))
done
"""
    result = _run_shizuku_text(shizuku, command, timeout_seconds)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise DeviceAccessError(message or "could not read captured screenshot")

    image_bytes = _decode_indexed_chunks(result.stdout, result.stderr, chunk_count)
    if len(image_bytes) != expected_size:
        raise DeviceAccessError(
            f"screenshot readback size mismatch: expected {expected_size}, got {len(image_bytes)}"
        )
    return image_bytes


def _decode_indexed_chunks(stdout: str, stderr: str, chunk_count: int) -> bytes:
    chunks: dict[int, bytes] = {}
    for match in CHUNK_RE.finditer(f"{stdout}\n{stderr}"):
        index = int(match.group(1))
        if index >= chunk_count:
            continue
        try:
            chunks[index] = base64.b64decode(match.group(2), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise DeviceAccessError(f"screenshot chunk {index + 1} was not valid base64") from exc

    missing = [index + 1 for index in range(chunk_count) if index not in chunks]
    if missing:
        preview = ", ".join(str(index) for index in missing[:5])
        raise DeviceAccessError(f"missing screenshot chunk(s): {preview}")
    return b"".join(chunks[index] for index in range(chunk_count))


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
    if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise DeviceAccessError("captured screenshot was not a PNG image")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)
    return output_path

from __future__ import annotations

import shlex
import shutil
import subprocess


class DeviceAccessError(RuntimeError):
    pass


def run_shizuku_shell(command: str, timeout_seconds: int = 30) -> str:
    shizuku = shutil.which("shizuku")
    if shizuku is None:
        raise DeviceAccessError("shizuku command is not available")

    try:
        completed = subprocess.run(
            [shizuku, "sh", "-c", command],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise DeviceAccessError("Shizuku timed out while running Android UI actions.") from exc

    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise DeviceAccessError(message or "Shizuku command failed")
    return "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)


def activity_package(activity: str) -> str:
    return activity.split("/", 1)[0]


def start_activity_commands(activity: str, settle_seconds: float = 1.0) -> list[str]:
    return [
        f"am start -n {shlex.quote(activity)} >/dev/null",
        f"sleep {settle_seconds:g}",
    ]


def return_to_package_commands(package: str, settle_seconds: float = 1.0) -> list[str]:
    return [
        f"monkey -p {shlex.quote(package)} 1 >/dev/null",
        f"sleep {settle_seconds:g}",
    ]


def window_focus_probe_command(limit: int = 5) -> str:
    return f"dumpsys window | grep -E \"mCurrentFocus|mFocusedApp\" | head -n {limit}"

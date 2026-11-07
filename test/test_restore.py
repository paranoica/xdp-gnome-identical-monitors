# runs the real portal backend against mock_mutter.py. a restore it rejects
# opens the share dialog on a headless mutter, so Start never replies, and
# that is how the tests tell the two cases apart
# usage: python3 -I test_restore.py <path to xdg-desktop-portal-gnome>

from __future__ import annotations

import itertools
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

PORTAL_NAME = "org.freedesktop.impl.portal.desktop.gnome"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENCAST = "org.freedesktop.impl.portal.ScreenCast"
MONITOR = 1
PERSIST_UNTIL_REVOKED = 2
DIALOG_TIMEOUT_MS = 3000
RESTORE_TIMEOUT_MS = 15000

LEFT = {
    "connector": "DVI-D-1",
    "vendor": "GSM",
    "product": "LG FULL HD",
    "serial": "0x01010101",
    "x": 0,
    "y": 0,
}
RIGHT = {**LEFT, "connector": "HDMI-1", "x": 1920}
DELL = {
    "connector": "DP-1",
    "vendor": "DEL",
    "product": "DELL U2414H",
    "serial": "0x12345678",
    "x": 1920,
    "y": 0,
}
LG_EDID = "GSM:LG FULL HD:0x01010101"

bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
counter = itertools.count(1)


def call(
    name: str,
    path: str,
    interface: str,
    method: str,
    args: GLib.Variant | None,
    timeout_ms: int = 5000,
) -> Any:
    # without NO_AUTO_START the bus would start the installed backend
    reply = bus.call_sync(
        name,
        path,
        interface,
        method,
        args,
        None,
        Gio.DBusCallFlags.NO_AUTO_START,
        timeout_ms,
        None,
    )
    return reply.unpack()


def set_layout(monitors: list[dict[str, Any]]) -> None:
    (serial,) = call(
        "test.MockMutter",
        "/test/MockMutter",
        "test.MockMutter.Control",
        "SetLayout",
        GLib.Variant("(s)", (json.dumps(monitors),)),
    )
    # the bus keeps message order, so once the mock has sent the new layout
    # our next call reaches the backend after it
    wait_until(lambda: served_serial() >= serial, "the backend to fetch the layout")


def served_serial() -> int:
    return call(
        "test.MockMutter",
        "/test/MockMutter",
        "test.MockMutter.Control",
        "ServedSerial",
        None,
    )[0]


def take_recorded() -> list[str]:
    return call(
        "test.MockMutter",
        "/test/MockMutter",
        "test.MockMutter.Control",
        "TakeRecorded",
        None,
    )[0]


def restore_data_for(match_string: str) -> GLib.Variant:
    streams = GLib.Variant(
        "(xxa(uuv))", (0, 0, [(0, MONITOR, GLib.Variant("s", match_string))])
    )
    return GLib.Variant("(suv)", ("GNOME", 1, streams))


def start_restored(
    restore_data: GLib.Variant, timeout_ms: int = RESTORE_TIMEOUT_MS
) -> dict[str, Any] | None:
    # None means the backend fell back to the dialog
    n = next(counter)
    session = f"/org/freedesktop/portal/desktop/session/1_1/test{n}"
    request = f"/org/freedesktop/portal/desktop/request/1_1/test{n}"

    response, _ = call(
        PORTAL_NAME,
        PORTAL_PATH,
        SCREENCAST,
        "CreateSession",
        GLib.Variant("(oosa{sv})", (request + "c", session, "", {})),
    )
    assert response == 0, f"CreateSession failed: {response}"

    options = {
        "types": GLib.Variant("u", MONITOR),
        "multiple": GLib.Variant("b", False),
        "persist_mode": GLib.Variant("u", PERSIST_UNTIL_REVOKED),
        "restore_data": restore_data,
    }
    response, _ = call(
        PORTAL_NAME,
        PORTAL_PATH,
        SCREENCAST,
        "SelectSources",
        GLib.Variant("(oosa{sv})", (request + "s", session, "", options)),
    )
    assert response == 0, f"SelectSources failed: {response}"

    try:
        response, results = call(
            PORTAL_NAME,
            PORTAL_PATH,
            SCREENCAST,
            "Start",
            GLib.Variant("(oossa{sv})", (request, session, "", "", {})),
            timeout_ms=timeout_ms,
        )
    except GLib.Error as error:
        if not error.matches(Gio.io_error_quark(), Gio.IOErrorEnum.TIMED_OUT):
            raise
        call(PORTAL_NAME, request, "org.freedesktop.impl.portal.Request", "Close", None)
        results = None
    else:
        assert response == 0, f"Start failed: {response}"

    call(PORTAL_NAME, session, "org.freedesktop.impl.portal.Session", "Close", None)
    return results


def stream_position(results: dict[str, Any]) -> tuple[int, int]:
    streams = results["streams"]
    assert len(streams) == 1, streams
    return streams[0][1]["position"]


def saved_match_string(results: dict[str, Any]) -> str:
    provider, version, (_, _, streams) = results["restore_data"]
    assert (provider, version) == ("GNOME", 1)
    assert len(streams) == 1, streams
    return streams[0][2]


def test_restores_left_twin() -> None:
    set_layout([LEFT, RIGHT])
    results = start_restored(restore_data_for(f"DVI-D-1:{LG_EDID}"))
    assert results is not None, "restore fell back to the dialog"
    assert take_recorded() == ["DVI-D-1"]
    assert stream_position(results) == (0, 0)
    assert saved_match_string(results) == f"DVI-D-1:{LG_EDID}"


def test_restores_right_twin() -> None:
    set_layout([LEFT, RIGHT])
    results = start_restored(restore_data_for(f"HDMI-1:{LG_EDID}"))
    assert results is not None, "restore fell back to the dialog"
    assert take_recorded() == ["HDMI-1"]
    assert stream_position(results) == (1920, 0)


def test_saved_data_survives_layout_reorder() -> None:
    set_layout([LEFT, RIGHT])
    first = start_restored(restore_data_for(f"HDMI-1:{LG_EDID}"))
    assert first is not None, "restore fell back to the dialog"
    take_recorded()

    set_layout([RIGHT, LEFT])
    second = start_restored(GLib.Variant("(suv)", ("GNOME", 1, _saved_streams(first))))
    assert second is not None, "restore fell back to the dialog"
    assert take_recorded() == ["HDMI-1"]


def _saved_streams(results: dict[str, Any]) -> GLib.Variant:
    _, _, (created, used, streams) = results["restore_data"]
    return GLib.Variant(
        "(xxa(uuv))",
        (created, used, [(i, t, GLib.Variant("s", s)) for i, t, s in streams]),
    )


def test_ambiguous_old_token_asks_again() -> None:
    set_layout([LEFT, RIGHT])
    results = start_restored(restore_data_for(LG_EDID), DIALOG_TIMEOUT_MS)
    assert take_recorded() == [], "an ambiguous token silently picked a monitor"
    assert results is None


def test_token_for_unplugged_twin_asks_again() -> None:
    set_layout([RIGHT])
    results = start_restored(restore_data_for(f"DVI-D-1:{LG_EDID}"), DIALOG_TIMEOUT_MS)
    assert take_recorded() == []
    assert results is None


def test_distinct_monitors_keep_old_tokens() -> None:
    set_layout([LEFT, DELL])
    results = start_restored(restore_data_for("DEL:DELL U2414H:0x12345678"))
    assert results is not None, "restore fell back to the dialog"
    assert take_recorded() == ["DP-1"]

    results = start_restored(restore_data_for(LG_EDID))
    assert results is not None, "restore fell back to the dialog"
    assert take_recorded() == ["DVI-D-1"]


def test_single_monitor_keeps_old_token() -> None:
    set_layout([RIGHT])
    results = start_restored(restore_data_for(LG_EDID))
    assert results is not None, "restore fell back to the dialog"
    assert take_recorded() == ["HDMI-1"]


TESTS: list[Callable[[], None]] = [
    test_restores_left_twin,
    test_restores_right_twin,
    test_saved_data_survives_layout_reorder,
    test_ambiguous_old_token_asks_again,
    test_token_for_unplugged_twin_asks_again,
    test_distinct_monitors_keep_old_tokens,
    test_single_monitor_keeps_old_token,
]


def wait_until(check: Callable[[], bool], what: str, timeout: float = 10.0) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if check():
            return
        time.sleep(0.1)
    raise TimeoutError(f"timed out waiting for {what}")


def screencast_exported() -> bool:
    try:
        (xml,) = call(
            PORTAL_NAME,
            PORTAL_PATH,
            "org.freedesktop.DBus.Introspectable",
            "Introspect",
            None,
        )
    except GLib.Error:
        return False
    return SCREENCAST in xml


def main() -> int:
    binary = sys.argv[1]
    runtime_dir = Path(os.environ["XDG_RUNTIME_DIR"])
    display = f"xdpg-test-{os.getpid()}"

    with tempfile.TemporaryDirectory(prefix="xdpg-test-logs-") as logs_dir:
        logs = Path(logs_dir)
        try:
            return run_all(binary, runtime_dir, display, logs)
        except Exception:
            for log in sorted(logs.iterdir()):
                print(f"--- {log.name}\n{log.read_text()}", file=sys.stderr)
            raise


def run_all(binary: str, runtime_dir: Path, display: str, logs: Path) -> int:
    with ExitStack() as stack:
        mutter_log = stack.enter_context(open(logs / "mutter.log", "w"))
        portal_log = stack.enter_context(open(logs / "portal.log", "w"))

        # own bus so mutter does not take the mocked names
        mutter = subprocess.Popen(
            [
                "dbus-run-session",
                "--",
                "mutter",
                "--headless",
                "--no-x11",
                "--wayland-display",
                display,
                "--virtual-monitor",
                "1280x720",
            ],
            stdout=mutter_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        stack.callback(stop_process_group, mutter)
        wait_until(lambda: (runtime_dir / display).exists(), "headless mutter")

        env = {
            k: v for k, v in os.environ.items() if k not in ("DISPLAY", "GDK_BACKEND")
        }
        env |= {"WAYLAND_DISPLAY": display, "XDG_SESSION_TYPE": "wayland"}
        portal = subprocess.Popen(
            [binary, "--replace"], env=env, stdout=portal_log, stderr=subprocess.STDOUT
        )
        stack.callback(stop_process, portal)
        wait_until(screencast_exported, "the ScreenCast backend")

        failed = 0
        for test in TESTS:
            try:
                test()
            except Exception:
                failed += 1
                print(f"not ok {test.__name__}")
                traceback.print_exc(limit=1)
            else:
                print(f"ok {test.__name__}")
        print(f"{len(TESTS) - failed}/{len(TESTS)} passed")
        return 1 if failed else 0


def stop_process(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def stop_process_group(process: subprocess.Popen[bytes]) -> None:
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


if __name__ == "__main__":
    sys.exit(main())

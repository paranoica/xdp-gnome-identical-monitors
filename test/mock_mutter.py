# fake org.gnome.Mutter.DisplayConfig and ScreenCast, just enough for
# xdg-desktop-portal-gnome. tests drive it through test.MockMutter.Control

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

CONTROL_NAME = "test.MockMutter"
CONTROL_PATH = "/test/MockMutter"

INTROSPECTION = """
<node>
  <interface name="org.gnome.Mutter.DisplayConfig">
    <signal name="MonitorsChanged" />
    <method name="GetCurrentState">
      <arg name="serial" direction="out" type="u" />
      <arg name="monitors" direction="out" type="a((ssss)a(siiddada{sv})a{sv})" />
      <arg name="logical_monitors" direction="out" type="a(iiduba(ssss)a{sv})" />
      <arg name="properties" direction="out" type="a{sv}" />
    </method>
  </interface>
  <interface name="org.gnome.Mutter.ScreenCast">
    <method name="CreateSession">
      <arg name="properties" type="a{sv}" direction="in" />
      <arg name="session_path" type="o" direction="out" />
    </method>
    <property name="Version" type="i" access="read" />
  </interface>
  <interface name="org.gnome.Mutter.ScreenCast.Session">
    <method name="Start" />
    <method name="Stop" />
    <signal name="Closed" />
    <method name="RecordMonitor">
      <arg name="connector" type="s" direction="in" />
      <arg name="properties" type="a{sv}" direction="in" />
      <arg name="stream_path" type="o" direction="out" />
    </method>
  </interface>
  <interface name="org.gnome.Mutter.ScreenCast.Stream">
    <signal name="PipeWireStreamAdded">
      <arg name="node_id" type="u" direction="out" />
    </signal>
    <property name="Parameters" type="a{sv}" access="read" />
  </interface>
  <interface name="test.MockMutter.Control">
    <method name="SetLayout">
      <arg name="layout_json" type="s" direction="in" />
      <arg name="serial" type="u" direction="out" />
    </method>
    <method name="ServedSerial">
      <arg name="serial" type="u" direction="out" />
    </method>
    <method name="TakeRecorded">
      <arg name="connectors" type="as" direction="out" />
    </method>
  </interface>
</node>
"""

NODE_INFO = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION)


def iface(name: str) -> Gio.DBusInterfaceInfo:
    return NODE_INFO.lookup_interface(name)


@dataclass
class MonitorSpec:

    connector: str
    vendor: str
    product: str
    serial: str
    x: int
    y: int
    width: int = 1920
    height: int = 1080
    builtin: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MonitorSpec:
        return cls(**data)


class MockMutter:

    def __init__(self, connection: Gio.DBusConnection) -> None:
        self.connection = connection
        self.layout: list[MonitorSpec] = []
        self.serial = 1
        self.served_serial = 0
        self.recorded: list[str] = []
        self.next_id = 0
        self.session_streams: dict[str, list[str]] = {}
        self.stream_params: dict[str, GLib.Variant] = {}

        self._register(
            "/org/gnome/Mutter/DisplayConfig", "org.gnome.Mutter.DisplayConfig"
        )
        self._register("/org/gnome/Mutter/ScreenCast", "org.gnome.Mutter.ScreenCast")
        self._register(CONTROL_PATH, "test.MockMutter.Control")

    def _register(self, path: str, interface: str) -> None:
        self.connection.register_object(
            path, iface(interface), self._on_method, self._on_get_property, None
        )

    def _on_get_property(
        self,
        _connection: Gio.DBusConnection,
        _sender: str,
        path: str,
        interface: str,
        prop: str,
    ) -> GLib.Variant | None:
        if interface == "org.gnome.Mutter.ScreenCast" and prop == "Version":
            return GLib.Variant("i", 4)
        if interface == "org.gnome.Mutter.ScreenCast.Stream" and prop == "Parameters":
            return self.stream_params[path]
        return None

    def _on_method(
        self,
        _connection: Gio.DBusConnection,
        _sender: str,
        path: str,
        interface: str,
        method: str,
        params: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        handler = getattr(self, f"_{interface.rsplit('.', 1)[-1]}_{method}", None)
        if handler is None:
            invocation.return_dbus_error(
                "org.freedesktop.DBus.Error.UnknownMethod", f"{interface}.{method}"
            )
            return
        handler(path, params.unpack(), invocation)

    def _DisplayConfig_GetCurrentState(
        self, _path: str, _args: tuple[()], invocation: Gio.DBusMethodInvocation
    ) -> None:
        monitors = []
        logical = []
        for spec in self.layout:
            ids = (spec.connector, spec.vendor, spec.product, spec.serial)
            mode = (
                f"{spec.width}x{spec.height}@60",
                spec.width,
                spec.height,
                60.0,
                1.0,
                [1.0],
                {
                    "is-current": GLib.Variant("b", True),
                    "is-preferred": GLib.Variant("b", True),
                },
            )
            # lets test-match-string.c see which layout the tracker has
            props = {
                "display-name": GLib.Variant(
                    "s", f"{spec.vendor} {spec.product} (layout {self.serial})"
                ),
                "is-builtin": GLib.Variant("b", spec.builtin),
            }
            monitors.append((ids, [mode], props))
            logical.append((spec.x, spec.y, 1.0, 0, spec is self.layout[0], [ids], {}))
        state = GLib.Variant(
            "(ua((ssss)a(siiddada{sv})a{sv})a(iiduba(ssss)a{sv})a{sv})",
            (self.serial, monitors, logical, {"layout-mode": GLib.Variant("u", 1)}),
        )
        self.served_serial = self.serial
        invocation.return_value(state)

    def _ScreenCast_CreateSession(
        self, _path: str, _args: tuple[dict], invocation: Gio.DBusMethodInvocation
    ) -> None:
        self.next_id += 1
        session_path = f"/org/gnome/Mutter/ScreenCast/Session/u{self.next_id}"
        self._register(session_path, "org.gnome.Mutter.ScreenCast.Session")
        self.session_streams[session_path] = []
        invocation.return_value(GLib.Variant("(o)", (session_path,)))

    def _Session_RecordMonitor(
        self, path: str, args: tuple[str, dict], invocation: Gio.DBusMethodInvocation
    ) -> None:
        connector = args[0]
        spec = next((m for m in self.layout if m.connector == connector), None)
        if spec is None:
            invocation.return_dbus_error(
                "org.freedesktop.DBus.Error.InvalidArgs", f"Unknown monitor {connector}"
            )
            return
        self.recorded.append(connector)
        self.next_id += 1
        stream_path = f"/org/gnome/Mutter/ScreenCast/Stream/u{self.next_id}"
        self.stream_params[stream_path] = GLib.Variant(
            "a{sv}",
            {
                "position": GLib.Variant("(ii)", (spec.x, spec.y)),
                "size": GLib.Variant("(ii)", (spec.width, spec.height)),
            },
        )
        self._register(stream_path, "org.gnome.Mutter.ScreenCast.Stream")
        self.session_streams[path].append(stream_path)
        invocation.return_value(GLib.Variant("(o)", (stream_path,)))

    def _Session_Start(
        self, path: str, _args: tuple[()], invocation: Gio.DBusMethodInvocation
    ) -> None:
        invocation.return_value(None)
        for node_id, stream_path in enumerate(self.session_streams[path], start=100):
            self.connection.emit_signal(
                None,
                stream_path,
                "org.gnome.Mutter.ScreenCast.Stream",
                "PipeWireStreamAdded",
                GLib.Variant("(u)", (node_id,)),
            )

    def _Session_Stop(
        self, path: str, _args: tuple[()], invocation: Gio.DBusMethodInvocation
    ) -> None:
        invocation.return_value(None)
        self.connection.emit_signal(
            None, path, "org.gnome.Mutter.ScreenCast.Session", "Closed", None
        )

    def _Control_SetLayout(
        self, _path: str, args: tuple[str], invocation: Gio.DBusMethodInvocation
    ) -> None:
        self.layout = [MonitorSpec.from_dict(m) for m in json.loads(args[0])]
        self.serial += 1
        invocation.return_value(GLib.Variant("(u)", (self.serial,)))
        self.connection.emit_signal(
            None,
            "/org/gnome/Mutter/DisplayConfig",
            "org.gnome.Mutter.DisplayConfig",
            "MonitorsChanged",
            None,
        )

    def _Control_ServedSerial(
        self, _path: str, _args: tuple[()], invocation: Gio.DBusMethodInvocation
    ) -> None:
        invocation.return_value(GLib.Variant("(u)", (self.served_serial,)))

    def _Control_TakeRecorded(
        self, _path: str, _args: tuple[()], invocation: Gio.DBusMethodInvocation
    ) -> None:
        recorded, self.recorded = self.recorded, []
        invocation.return_value(GLib.Variant("(as)", (recorded,)))


def main() -> int:
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    mock = MockMutter(connection)
    loop = GLib.MainLoop()
    pending = {
        "org.gnome.Mutter.DisplayConfig",
        "org.gnome.Mutter.ScreenCast",
        CONTROL_NAME,
    }

    def on_acquired(_connection: Gio.DBusConnection, name: str) -> None:
        pending.discard(name)
        if not pending:
            print("ready", flush=True)

    def on_lost(_connection: Gio.DBusConnection, name: str) -> None:
        print(f"lost bus name {name}", file=sys.stderr, flush=True)
        loop.quit()

    for name in sorted(pending):
        Gio.bus_own_name_on_connection(
            connection, name, Gio.BusNameOwnerFlags.NONE, on_acquired, on_lost
        )
    loop.run()
    del mock
    return 1


if __name__ == "__main__":
    sys.exit(main())

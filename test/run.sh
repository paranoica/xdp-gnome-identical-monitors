#!/usr/bin/env bash
# usage: test/run.sh <xdp-gnome source dir> <its meson build dir>
set -euo pipefail

src=$(realpath "$1")
build=$(realpath "$2")
here=$(dirname "$(realpath "$0")")
out=$(mktemp -d "${TMPDIR:-/tmp}/xdpg-test.XXXXXX")
trap 'rm -rf "$out"' EXIT

cc -o "$out/test-match-string" \
  "$here/test-match-string.c" \
  "$src/src/displaystatetracker.c" \
  "$build/src/shell-dbus.c" \
  -I"$build/src" -I"$build" -I"$src/src" \
  $(pkg-config --cflags --libs gtk4 gio-unix-2.0) -lm

export XDPG_TEST_OUT=$out XDPG_TEST_HERE=$here XDPG_TEST_BINARY=$build/src/xdg-desktop-portal-gnome

# keep the test processes off the real dconf, gvfs and a11y bus
export GSETTINGS_BACKEND=memory GIO_USE_VFS=local GTK_A11Y=none NO_AT_BRIDGE=1

# build chroots have no runtime dir and headless mutter needs one
if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
  export XDG_RUNTIME_DIR=$out/runtime
  mkdir -m 700 "$XDG_RUNTIME_DIR"
fi

dbus-run-session -- bash -euo pipefail -c '
  python3 -I "$XDPG_TEST_HERE/mock_mutter.py" > "$XDPG_TEST_OUT/mock.log" 2>&1 &
  for _ in $(seq 50); do grep -q ready "$XDPG_TEST_OUT/mock.log" && break; sleep 0.1; done
  grep -q ready "$XDPG_TEST_OUT/mock.log" || { cat "$XDPG_TEST_OUT/mock.log"; exit 1; }

  status=0
  echo "== unit: match strings"
  "$XDPG_TEST_OUT/test-match-string" || status=1

  echo "== integration: screencast restore"
  python3 -I "$XDPG_TEST_HERE/test_restore.py" "$XDPG_TEST_BINARY" || status=1
  exit $status
'

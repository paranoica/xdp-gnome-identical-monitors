#!/usr/bin/env bash
# usage: pacman-hook/test.sh [check script]
set -euo pipefail

here=$(dirname "$(realpath "$0")")
script=$(realpath "${1:-$here/check-patched-gnome-packages}")
fake=$(mktemp -d)
trap 'rm -rf "$fake"' EXIT

# FAKE_INSTALLED and FAKE_REPO are space separated name=version lists
cat >"$fake/pacman" <<'EOF'
#!/usr/bin/env bash
lookup() {
  local name=$1 entry
  for entry in $2; do
    if [ "${entry%%=*}" = "$name" ]; then
      printf '%s\n' "${entry#*=}"
      return 0
    fi
  done
  return 1
}
case $1 in
  -Q)
    version=$(lookup "$2" "${FAKE_INSTALLED:-}") || { echo "error: package '$2' was not found" >&2; exit 1; }
    echo "$2 $version"
    ;;
  -Si)
    version=$(lookup "$2" "${FAKE_REPO:-}") || { echo "error: package '$2' was not found" >&2; exit 1; }
    printf 'Repository      : extra\nName            : %s\nVersion         : %s\nDescription     : x\n' "$2" "$version"
    ;;
esac
EOF
chmod +x "$fake/pacman"

failed=0

check() {
  local name=$1 installed=$2 repo=$3 expected=$4 output
  output=$(PATH="$fake:$PATH" FAKE_INSTALLED=$installed FAKE_REPO=$repo "$script")
  if [ "$output" = "$expected" ]; then
    echo "ok $name"
  else
    echo "not ok $name"
    printf '  expected: %q\n  got:      %q\n' "$expected" "$output"
    failed=1
  fi
}

both_installed="mutter-lma=51.1-1 xdg-desktop-portal-gnome-identical-monitors=51.0-1"

check "same versions: silent" \
  "$both_installed" \
  "mutter=51.1-1 xdg-desktop-portal-gnome=51.0-1" \
  ""

check "only pkgrel bumped in the repos: silent" \
  "$both_installed" \
  "mutter=51.1-3 xdg-desktop-portal-gnome=51.0-2" \
  ""

check "newer mutter: warns about mutter-lma only" \
  "$both_installed" \
  "mutter=51.2-1 xdg-desktop-portal-gnome=51.0-1" \
  "warning: mutter 51.2-1 is in the repos, but the installed patched build is mutter-lma 51.1-1.
         Rebuild mutter-lma on mutter 51.2."

check "both newer (major release): warns about both" \
  "$both_installed" \
  "mutter=52.0-1 xdg-desktop-portal-gnome=52.0-1" \
  "warning: mutter 52.0-1 is in the repos, but the installed patched build is mutter-lma 51.1-1.
         Rebuild mutter-lma on mutter 52.0.
warning: xdg-desktop-portal-gnome 52.0-1 is in the repos, but the installed patched build is xdg-desktop-portal-gnome-identical-monitors 51.0-1.
         Rebuild xdg-desktop-portal-gnome-identical-monitors on xdg-desktop-portal-gnome 52.0."

check "pre-release ordering: 52alpha is newer than 51.1" \
  "mutter-lma=51.1-1" \
  "mutter=52alpha-1" \
  "warning: mutter 52alpha-1 is in the repos, but the installed patched build is mutter-lma 51.1-1.
         Rebuild mutter-lma on mutter 52alpha."

check "patched build newer than the repos: silent" \
  "$both_installed" \
  "mutter=51.0-1 xdg-desktop-portal-gnome=50.2-1" \
  ""

check "patched package not installed: silent" \
  "" \
  "mutter=52.0-1 xdg-desktop-portal-gnome=52.0-1" \
  ""

check "repo package missing: silent" \
  "$both_installed" \
  "" \
  ""

exit $failed

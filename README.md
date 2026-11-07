# xdp-gnome-identical-monitors

Patch for xdg-desktop-portal-gnome 51.0 plus an Arch package.

Two monitors of the same model can report the same EDID vendor, product and
serial. Mine are two LG panels that both say `GSM:LG FULL HD:0x01010101`.
The portal saves screencast restore data with exactly that string, so when a
session is restored it always gets the twin that comes first, no matter which
one was picked. Chrome hits this on every screen share, because the capture
runs in a second portal session restored from the token of the first one. The
preview in the picker is right, the shared stream is the other monitor.

Upstream fixed the same thing for VMs (`unknown:unknown:unknown`, commit
9d79066), but not for real monitors with a duplicated EDID.

The patch prefixes the connector to the match string when two connected
monitors share it, e.g. `HDMI-1:GSM:LG FULL HD:0x01010101`. Monitors with a
unique EDID keep the old string, so their saved tokens keep working. Tokens
saved for one of the twins before the patch make the portal ask once more.

Upstream: [GNOME/xdg-desktop-portal-gnome!276](https://gitlab.gnome.org/GNOME/xdg-desktop-portal-gnome/-/merge_requests/276),
fixes [#131](https://gitlab.gnome.org/GNOME/xdg-desktop-portal-gnome/-/issues/131).
Once it lands in a release, this package is not needed anymore.

## Install

```sh
makepkg -si
systemctl --user restart xdg-desktop-portal-gnome
```

It replaces the stock package and does not follow its updates, so bump
`pkgver` and rebuild when Arch moves on. Sources come from the GNOME mirrors on
GitHub because gitlab.gnome.org blocks makepkg. The b2sums are the same as in
the Arch package, which verifies the signed tags.

Back to stock: `sudo pacman -S xdg-desktop-portal-gnome`

## Tests

`check()` runs them, or by hand:

```sh
test/run.sh path/to/xdg-desktop-portal-gnome path/to/build
```

Needs dbus, mutter and python-gobject. Everything runs on a private session
bus with a fake mutter, and the real portal binary draws its dialogs on a
headless mutter. On stock 51.0 the tests for twins fail, the rest pass. A
build in a clean chroot needs `--nocheck` since the tests live outside the
sources.

## Update reminder

`pacman-hook/` warns after a pacman transaction when the repos have a newer
`xdg-desktop-portal-gnome` or `mutter` than the patched builds installed here
(this one and `mutter-lma`).

```sh
sudo install -Dm755 -t /usr/local/bin pacman-hook/check-patched-gnome-packages
sudo install -Dm644 -t /etc/pacman.d/hooks pacman-hook/patched-gnome-packages.hook
```

## License

LGPL-2.1-or-later, same as xdg-desktop-portal-gnome.

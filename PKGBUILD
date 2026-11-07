# Maintainer: paranoica <mitjumper@gmail.com>
# Contributor: Fabian Bornschein <fabiscafe@archlinux.org>
# Contributor: Jan Alexander Steffens (heftig) <heftig@archlinux.org>

pkgname=xdg-desktop-portal-gnome-identical-monitors
_pkgname=xdg-desktop-portal-gnome
pkgver=51.0
pkgrel=1
pkgdesc="Backend implementation for xdg-desktop-portal for the GNOME desktop environment (restores screencasts on the right one of two identical monitors)"
url="https://github.com/paranoica/xdp-gnome-identical-monitors"
arch=(x86_64)
license=(LGPL-2.1-or-later)
depends=(
  cairo
  dconf
  fontconfig
  gdk-pixbuf2
  glib2
  glibc
  gnome-desktop-4
  graphene
  gtk4
  libadwaita
  libgcc
  libx11
  nautilus
  wayland
  xdg-desktop-portal
  'xdg-desktop-portal-gtk>=1.10.0-2'
)
makedepends=(
  git
  glib2-devel
  meson
)
checkdepends=(
  dbus
  mutter
  python-gobject
)
optdepends=('evince: Print previews')
provides=("$_pkgname=$pkgver" xdg-desktop-portal-impl)
conflicts=("$_pkgname" 'xdg-desktop-portal-gtk<1.10.0-2')
# gitlab.gnome.org blocks makepkg, the sums match the signed tags in the arch package
source=(
  "git+https://github.com/GNOME/xdg-desktop-portal-gnome.git#tag=$pkgver"
  "git+https://github.com/GNOME/libgxdp.git#commit=df896e3412b749947bc6f62a91a1aac8e6b6d19b"
  0001-displaystatetracker-Tell-apart-monitors-with-identical-EDID.patch
)
b2sums=('e741415df2143c413def3e1f4e4821258ed541d84537f8cd2d462a3003580f8d3a80b617bcc441ea77371254a132fbbbae0ae97e1777cf8de0c2a770327c640d'
        'f5bd238c316a55784f97b1b7c8b498d3dfa727375cf8a1bf61f4771e306232b36752df8f61edb8d8c5da7c5e1a7acd8c0e85a53725af56e9b18b8dd1a6f284e0'
        '9931a93475547afc7fdbf3772ef17179cceea87bb8de66a3099d025f39cf088398ee2c24bd0566a62a6736e5d1eafa57a4a290e9dc806f2ffb302773837ef8f7')

prepare() {
  cd $_pkgname
  git apply -3 ../0001-displaystatetracker-Tell-apart-monitors-with-identical-EDID.patch
}

build() {
  # use the libgxdp checkout instead of the meson wrap
  export MESON_PACKAGE_CACHE_DIR="$srcdir"

  arch-meson $_pkgname build
  meson compile -C build
}

check() {
  meson test -C build --print-errorlogs
  # tests live outside srcdir, a clean chroot build needs --nocheck
  bash "$startdir"/test/run.sh "$srcdir/$_pkgname" "$srcdir/build"
}

package() {
  meson install -C build --no-rebuild --destdir "$pkgdir"
}

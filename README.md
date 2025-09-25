# Terminator 2

Terminator 2 is a next-generation terminal emulator being rewritten in Rust on
 top of GTK 4, VTE, and the modern GNOME stack. The goal is to recreate and
 extend the powerful tiling, grouping, and broadcasting workflow of the original
 Terminator while modernising the codebase and user experience.

This repository currently contains the initial prototype: a GTK 4 window with a
terminator titlebar and embedded VTE widget. The long-term specification is
captured in `specs.md`.

## Project Status
- ✅ Rust + GTK 4 application skeleton
- ✅ Embedded VTE terminal widget
- 🚧 Layout, grouping, configuration, and DBus features (see `specs.md`)

## Build Requirements
Terminator 2 links against GTK 4, Graphene, and the GTK 4 flavour of VTE. You
need both the Rust toolchain (rustc/cargo 1.90 or newer) and the native
libraries.

On Debian/Ubuntu you can install GTK and Graphene from packages:

```bash
sudo apt install libgtk-4-dev libgraphene-1.0-dev
```

As of late 2024, the GTK 4 VTE bindings (`vte-2.91-gtk4.pc`) are not available
in the stable Debian/Ubuntu archives. To satisfy the Rust `vte4` crate you need
VTE built with GTK 4 support. Options:

1. **Use a distro package if available** (e.g. `libvte-2.91-gtk4-dev`). After
   installation verify with:
   ```bash
   pkg-config --modversion vte-2.91-gtk4
   ```

2. **Build VTE from source**:
   ```bash
   sudo apt install build-essential meson ninja-build libgtk-4-dev \
        gobject-introspection libpcre2-dev libgnutls28-dev valac
   git clone https://gitlab.gnome.org/GNOME/vte.git
   cd vte
   meson setup build -Dgtk4=true
   ninja -C build
   sudo ninja -C build install
   ```
   Ensure `pkg-config` can find the new `.pc` file:
   ```bash
   export PKG_CONFIG_PATH=/usr/local/lib/x86_64-linux-gnu/pkgconfig:$PKG_CONFIG_PATH
   pkg-config --modversion vte-2.91-gtk4
   ```

Once the command prints a version number, you are ready to build Terminator 2.

## Building
Build a release binary in the repository root:

```bash
make
```

This compiles with `cargo build --release` and copies the resulting binary to
`./terminator2`.

For iterative development you can use:

```bash
cargo run        # debug build
cargo build      # debug build only
cargo build --release
```

## Running
After `make` completes, launch the prototype with:

```bash
./terminator2
```

You should see a GTK window titled “Terminator 2” with a single VTE terminal
embedded in the content area.

## Specification
The full functional specification – covering tiling layouts, grouping,
configuration, DBus control, plugin architecture, and more – is maintained in
[`specs.md`](specs.md). The implementation roadmap follows that document.

## Contributing
Development is in its early stages. Bug reports, ideas, and pull requests are
welcome; please review the spec and align changes with the planned architecture.


## Keyboard Shortcuts
Terminator 2 binds the traditional Terminator key layout by default (e.g. `<Ctrl><Shift>T>` for a new tab, `<Ctrl><Shift>O/E>` for splits).
Right-click inside a terminal to see the context menu with the current shortcuts, or open **Settings** to edit them.

# Repository Guidelines

This guide helps contributors work efficiently in this repository.

## Project Structure & Module Organization
- `terminatorlib/`: Core Python/GTK code (VTE integration, menus, config, plugins).
- `terminator`: Launcher script for the application.
- `remotinator`: Helper script for remote control.
- `data/`: Desktop file, icons, appdata.
- `po/`: Translations (.po). See `TRANSLATION.md`.
- `doc/`: Manpages and documentation sources.
- `tests/`: Pytest-based unit tests.
- `completion/`: Shell completion files.

## Build, Test, and Development Commands
- Install editable with test deps: `pip install -e .[test]`
- Build assets and translations: `python setup.py build`
- Run tests: `pytest -q`
- Launch locally from source: `./terminator`

Notes:
- `python setup.py build` compiles .po files and merges desktop/appdata. Use `--without-gettext` if gettext is unavailable.

## Coding Style & Naming Conventions
- Language: Python 3; 4-space indentation; UTF-8 encoding.
- Naming: modules/functions `snake_case`, classes `CapWords`.
- Imports: standard library, third-party, then local (grouped); avoid unused imports.
- Strings shown to users must be wrapped with `_()` for translation (from `terminatorlib.translation`).
- Keep changes minimal and consistent with surrounding code. Follow existing patterns in `terminatorlib/` (e.g., menu items in `terminatorlib/terminal_popup_menu.py`).

## Testing Guidelines
- Use pytest. Place tests under `tests/` and name files `test_*.py`.
- Prefer parametrization (`@pytest.mark.parametrize`) as in `tests/test_prefseditor_keybindings.py`.
- Run `pytest` before opening a PR. Add tests for new behavior when practical.

## Commit & Pull Request Guidelines
- Commits: concise, imperative mood; one logical change per commit. Reference issues (e.g., `Fix #123: describe change`).
- PRs: include a clear description, steps to reproduce/verify, linked issues, and screenshots for UI changes.
- Ensure `pytest` passes and `python setup.py build` succeeds. Update docs, translations, and icons if affected.

## Security & Configuration Tips
- Favor GLib/Gtk/VTE APIs over shelling out. Validate external inputs. Avoid blocking the GTK main loop.
- When touching clipboard, URLs, or plugins, reuse existing helpers in `terminatorlib/` and follow translation rules in `TRANSLATION.md`.

## Agent-Specific Notes
- Respect these guidelines for any automated edits. Do not modify unrelated files. Keep diffs focused and follow existing menu/translation patterns.


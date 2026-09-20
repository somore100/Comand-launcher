# Changelog

All notable changes to Command Vault are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## Unreleased

### Added

* Single-instance lock. A second launch (from autostart, a global hotkey, or just double-clicking the icon again) now asks the already-running instance to raise its window and exits, instead of starting a competing process that could double-register hotkeys or race on `commands.json`.
* Corrupted `commands.json` recovery. A malformed data file (partial write from a crash, bad manual edit, disk issue) no longer prevents the app from starting. It's quarantined as `commands.json.corrupted-<timestamp>`, the app warns you, and starts with an empty vault instead of crashing.
* Export / Import vault. Settings → Data Storage now has "Export Vault..." and "Import Vault..." — cheap insurance before big edits or moving to a new machine. Import confirms before replacing anything, automatically backs up your current vault first, and re-registers hotkeys/autostart entries from the imported file on this machine.
* Auto-update check. Settings → Updates shows your current version and a "Check for Updates" button; by default the app also checks automatically about once a day and lets you know if a newer release is out. Can be turned off from the same section.

### Changed

* Replaced the placeholder padlock icon with the real Command Vault logo across `packaging/icon.png` / `icon.ico` / `icon.icns`, the system tray icon, and the app's own titlebar icon.

### Fixed

* App-level "run on startup" doing nothing on the AppImage build. Autostart was launching the AppImage directly from the `.desktop` file's `Exec=` line, which has to FUSE-mount itself right as the desktop session starts — a well-known race against DBus/`XDG_RUNTIME_DIR` not being up yet. Autostart now runs through a wrapper script that uses `--appimage-extract-and-run` (sidesteps FUSE for that one launch), defensively re-applies the executable bit, and adds a short startup delay that isn't GNOME-specific. Applied to both the app-level autostart and per-entry AppImage-type autostart entries.
* Entries launched via "Run" inheriting Command Vault's own `APPIMAGE`/`APPDIR`/`ARGV0`/`OWD` environment variables when Command Vault itself is running as an AppImage. A launched script or app that happens to also check `APPIMAGE` would see it pointing at Command Vault's own binary, only when launched via Command Vault's Run button — not when run standalone. Those AppImage-runtime variables are now stripped from the environment of anything Command Vault launches.

## v1.5.0 — 2026-08-26

README polish (badges, screenshots, reorganized build instructions, Contributing section) — no functional/`main.py` changes from v1.4.0.

## v1.4.0 — 2026-08-25

The first release with the full accumulated feature set: categories and custom icons, multiline commands, `.sh`/`.bat`/`.ps1`/`.py`/AppImage auto-detection, terminal vs. silent run mode with a live console log panel, templated `{{name}}` commands, "Run All", app-level and per-entry autostart, global hotkeys (app-level and per-entry, with conflict detection and a system tray icon), a custom terminal picker, configurable data storage with migration, and "Pick Installed App". See `README.md` for the full current feature list.

## v1.0.0 – v1.3.1

These tags exist in the repository but all point at the same initial commit — a development-environment mixup meant every "replace this file" edit across several early sessions landed in the parent folder instead of the actual repo, so nothing from that period was ever actually committed. Nothing was lost (the real work carried forward and shipped in v1.4.0); listed here only so the gap in tagged history doesn't look like a mistake in this file.

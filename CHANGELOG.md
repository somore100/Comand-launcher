# Changelog

All notable changes to Command Vault are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## Unreleased

### Added

* Persistent browser profile for browser-automation bots. A new per-entry option in the Edit Entry dialog gives a Playwright/Selenium script a profile folder that survives between runs, so it stays logged in instead of starting fresh each time. The folder's path is passed to the script in the `COMMAND_VAULT_BROWSER_PROFILE` environment variable, for the Run button (both modes), autostart, and scheduled runs. Leave the folder blank for an automatic per-entry one (outside the vault folder, so it isn't part of Export Vault), or pick your own; Reset deletes it, and deleting an entry offers to remove its automatic profile. A starter script is in `examples/playwright_bot.py`.
* Per-entry scheduling. Each entry can now be set to "Run on a schedule" — daily, or on chosen weekdays, at a specific 24h time — from the Edit Entry dialog. Registered with the OS scheduler (a per-entry `cron` line on Linux/macOS, a Task Scheduler task on Windows) rather than an in-app timer, so it fires even if Command Vault isn't open. The cron path only ever touches the single line it owns in your crontab (tagged with a per-entry marker comment) — everything else already in your crontab is read and written back untouched. Scheduled runs always execute silently in the background, regardless of the entry's Run Mode (there's no terminal to attach at an unattended run). The entry list shows a "Sched" column with the configured time when a schedule is active.
* Single-instance lock. A second launch (from autostart, a global hotkey, or just double-clicking the icon again) now asks the already-running instance to raise its window and exits, instead of starting a competing process that could double-register hotkeys or race on `commands.json`. Backed by an OS-level exclusive file lock (not a fixed port), so it can't silently fail open if something else happens to be using a particular port; the "raise window" signal itself goes over an OS-assigned ephemeral port and requires a per-run token written to a user-only (`0600`) lock file, so another local process — or another user on a shared machine — can't trigger it.
* Unit tests (`tests/test_main.py`, run with `pytest`) covering the data layer (normalize/load/save, atomic writes, `.bak` recovery), `resolve_exec_command`, placeholder extraction/filling, update-check version parsing, and the single-instance lock.
* macOS build workflow (`.github/workflows/build-macos.yml`), producing `.dmg`s for both Apple Silicon and Intel. Unsigned/not notarized for now, so Gatekeeper needs a first-run workaround -- documented in the README.
* Corrupted `commands.json` recovery. A malformed data file (partial write from a crash, bad manual edit, disk issue) no longer prevents the app from starting. It's quarantined as `commands.json.corrupted-<timestamp>`, the app warns you, and it now recovers from the automatic `commands.json.bak` (see below) instead of starting empty, if a usable backup exists.
* Atomic, backed-up saves. Every save now writes to a temp file and `os.replace()`s it into place, so a crash or power loss mid-write can no longer corrupt `commands.json` in the first place (previously the exact scenario the recovery above exists to handle). Each save also rolls the previous file to `commands.json.bak` first, which the recovery path above now uses.
* Export / Import vault. Settings → Data Storage now has "Export Vault..." and "Import Vault..." — cheap insurance before big edits or moving to a new machine. Import confirms before replacing anything, automatically backs up your current vault first, and re-registers hotkeys/autostart entries from the imported file on this machine.
* Auto-update check. Settings → Updates shows your current version and a "Check for Updates" button; by default the app also checks automatically about once a day and lets you know if a newer release is out. Can be turned off from the same section.

### Changed

* Internal: split the ~3,200-line `main.py` into a `cmdvault/` package (data layer, autostart, scheduling, single-instance lock, update check, terminals, placeholders, entry/settings dialogs, hotkeys/tray, main window). `main.py` is now just the entry point; behavior is unchanged. Tests now import and patch the individual modules.
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

# Command Vault roadmap

Ordered work list. Update as items ship.

## Done
- UI fits small screens (scrollable dialogs, pinned buttons, main window top bar/columns) - 1.7.0
- 1.7.0 released (AppImage, exe, macOS dmg)
- Optional administrator rights for `sudo` entries on Linux/macOS (off / ask / remember via exact sudoers rule)

## Next
1. **Builds** (commit the pending `build.yml`): .deb / .rpm / Arch packages, Intel macOS on `macos-15-intel`, bump actions off Node 20. Check packages on a real Fedora.
2. **Windows admin rights**: "ask" = elevated launch (UAC); "remember" = Task Scheduler task with highest privileges, created once with one UAC approval.
3. **Record bot**: record a website routine with `playwright codegen` + the entry's persistent browser profile, run headless on schedule/boot (e.g. start an Aternos server). Verify codegen + persistent profile on Fedora/Pop!_OS first. Caveats: captchas/2FA, site terms of service, Aternos start queue / "are you still there" confirmations, headless detection.
4. **Starter template** for new bot entries.
5. **App interactions** (new): after launching an app, run steps inside it, e.g. open Firefox and restore the previous session with one click.
   - Firefox specifically: better done through its own settings than clicks (a per-entry profile with `browser.startup.page = 3` in `user.js`, or `firefox -P <profile>`); Ctrl+Shift+T only reopens the last closed window.
   - Generic version: an ordered "after launch" step list (wait N seconds / wait for a window, send keys, click). Needs `xdotool` on X11; native Wayland blocks synthetic input (would need `ydotool`/portals) - decide support level first. Windows could use PowerShell/AutoHotkey, macOS `osascript`.
   - Earlier a step-list editor was rejected for web bots, but for native apps it is the simplest option.

## Known gaps / unverified
- Windows scheduled-run status wrapper and Task Scheduler paths never run on real Windows.
- Cron/terminal/tray/hotkeys only unit-tested in a sandbox; admin-rights install (pkexec) not yet tried on real machines.
- Scheduling/autostart not re-applied on Import Vault; "+ Add many" doesn't set autostart/schedule/hotkey/browser profile/admin mode.
- No macOS autostart. macOS builds unsigned/not notarized.
- Two overlapping runs of one browser-profile entry fail on the profile lock.

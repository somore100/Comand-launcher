# Command Vault

**A lightweight launcher for your own scripts, tools, and apps** — no more `cd`-ing into folders and running `./script.sh` by hand.

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

Save any command, script, or AppImage once, organize it by category, and launch it with one click — in a terminal or silently in the background.

<p align="center">
  <img width="49%" alt="Command Vault main window" src="https://github.com/user-attachments/assets/a066ba84-a7d9-4d5c-83b8-f29367e4acf7" />
  <img width="49%" alt="Command Vault entry settings" src="https://github.com/user-attachments/assets/6190c615-2150-48ca-8af9-fc6eb32b748a" />
</p>

## Features

- **One-click launching** for shell commands, multi-line scripts, `.sh` / `.bat` / `.ps1` / `.py` files, and AppImages
- **Categories** to organize tools (e.g. AI Tools, Dev Environments, Media)
- **Custom icons** per entry, picked from a built-in emoji grid
- **Working directory** support — no need to bake `cd` into your commands
- **Terminal or silent mode** — open a terminal window, or run detached in the background
- **Autostart** — launch Command Vault itself at login, and/or set individual entries to start automatically on boot (works independently of whether Command Vault is running)
- **Pick Installed App** — browse your system's installed applications directly (`.desktop` files on Linux, Start Menu shortcuts on Windows) instead of hunting for paths
- **Configurable data storage** — commands are stored in an organized, OS-appropriate folder by default (`~/.local/share/command-vault` on Linux, `%APPDATA%\CommandVault` on Windows), and you can change the location from Settings

## Downloads

Prebuilt binaries are attached to each [release](../../releases):

| Platform | File |
|---|---|
| Linux | `CommandVault-x86_64.AppImage` — make it executable (`chmod +x`) and run it |
| Windows | `CommandVault.exe` |

## Running from source

Requires Python 3.9+ with Tk support (`python3-tk` on Debian/Ubuntu-based systems; bundled with the standard installer on Windows).

```bash
python3 main.py
```

## Building it yourself

Builds are automated via GitHub Actions (see [`.github/workflows/build.yml`](.github/workflows/build.yml)), which produces both the Linux AppImage and Windows exe on every tagged release (`vX.Y.Z`) or manual workflow run.

**Linux:**
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name CommandVault --icon packaging/icon.ico main.py
# then wrap dist/CommandVault into an AppImage using appimagetool + packaging/command-vault.desktop
```

**Windows:**
```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name CommandVault --icon packaging/icon.ico main.py
```

## Contributing

Issues and pull requests are welcome — especially around packaging for additional platforms (e.g. a macOS build) or new launch modes.

## License

MIT — see [LICENSE](LICENSE).

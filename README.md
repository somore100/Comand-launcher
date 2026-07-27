# Command Vault

A lightweight launcher for your own scripts, tools, and apps — no more `cd`-ing into folders and running `./script.sh` by hand.

Save any command, script, or AppImage once, organize it by category, and launch it with one click — in a terminal or silently in the background.

![screenshot placeholder](packaging/icon.png)

## Features

- **One-click launching** for shell commands, multi-line scripts, `.sh` / `.bat` / `.ps1` / `.py` files, and AppImages
- **Categories** to organize tools (e.g. AI Tools, Dev Environments, Media)
- **Custom icons** per entry, picked from a built-in emoji grid
- **Working directory** support — no need to bake `cd` into your commands
- **Terminal or silent mode** — open a terminal window, or run detached in the background
- **Autostart** — launch Command Vault itself at login, and/or set individual entries to start automatically on boot (works independently of whether Command Vault is running)
- **Pick Installed App** — browse your system's installed applications directly (`.desktop` files on Linux, Start Menu shortcuts on Windows) instead of hunting for paths
- **Configurable data storage** — commands are stored in an organized, OS-appropriate folder by default (`~/.local/share/command-vault` on Linux, `%APPDATA%\CommandVault` on Windows), and you can change the location from Settings

## Running from source

Requires Python 3.9+ with Tk support (`python3-tk` on Debian/Ubuntu-based systems; bundled with the standard installer on Windows).

```bash
python3 main.py
```

## Downloads

Prebuilt binaries are attached to each [release](../../releases):

- **Linux**: `CommandVault-x86_64.AppImage` — make it executable (`chmod +x`) and run it
- **Windows**: `CommandVault.exe`

## Building it yourself

Builds are automated via GitHub Actions (see `.github/workflows/build.yml`), which produces both the Linux AppImage and Windows exe on every tagged release (`vX.Y.Z`) or manual workflow run.

To build locally on Linux:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name CommandVault --icon packaging/icon.ico main.py
# then wrap dist/CommandVault into an AppImage using appimagetool + packaging/command-vault.desktop
```

To build locally on Windows:

```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name CommandVault --icon packaging/icon.ico main.py
```

## License

MIT — see [LICENSE](LICENSE).

"""Command Vault entry point."""
import sys
from cmdvault.app import CommandVault
from cmdvault.instance import notify_running_instance


if __name__ == "__main__":
    if notify_running_instance():
        # Another instance is already running and has been asked to raise
        # its window -- nothing more for this process to do.
        sys.exit(0)
    app = CommandVault()
    app.mainloop()

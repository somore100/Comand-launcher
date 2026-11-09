"""Command Vault entry point."""
import sys
from cmdvault.app import CommandVault
from cmdvault.instance import notify_running_instance


if __name__ == "__main__":
    if "--mcp" in sys.argv[1:]:
        # Headless Model Context Protocol server for AI assistants (see cmdvault/mcp_server.py).
        from cmdvault.mcp_server import serve
        sys.exit(serve())
    if notify_running_instance():
        # Another instance is already running and has been asked to raise
        # its window -- nothing more for this process to do.
        sys.exit(0)
    app = CommandVault()
    app.mainloop()

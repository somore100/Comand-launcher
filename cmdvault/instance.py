"""instance -- split out of the former monolithic main.py."""
import json
import os
import secrets
import socket
import threading
from .data import app_config_dir
from .platform_utils import is_windows


# Single-instance lock
# ---------------------------------------------------------------------------
# Autostart + a global hotkey can each independently launch/wake an
# instance, so nothing previously stopped two copies running at once --
# both trying to register the same OS-level hotkeys, or both writing
# commands.json at overlapping moments, is a real failure mode.
#
# This used to be a hardcoded TCP port (127.0.0.1:47812) doing double duty
# as both the mutex and the IPC channel. Two problems with that: (1) if
# binding failed for any OTHER reason -- something unrelated already using
# that port, security software, a stale reservation -- the app just
# proceeded unlocked, silently allowing two full instances to run at once;
# and (2) the port was fixed and unauthenticated, so any local process --
# including another user's, on a shared machine -- could connect and
# trigger the window to pop up, since nothing proved the caller was
# actually another launch of Command Vault.
#
# Now an OS-level exclusive file lock is the actual source of truth for
# "am I the only instance" -- it doesn't depend on any particular port
# being free, and the OS releases it automatically if the process dies, so
# a crash can never leave a stale lock behind. Whichever process wins that
# lock opens a TCP listener on an OS-assigned ephemeral port (127.0.0.1
# only, to avoid any firewall prompt on Windows) and publishes {port,
# token} into the lock file, which is chmod'd to the current user only on
# POSIX. A later launch that loses the file lock reads that info and must
# present the matching token before the running instance will raise its
# window; anything else (wrong token, no published info, connection
# refused) is silently ignored.

def _instance_lock_path():
    return os.path.join(app_config_dir(), "instance.lock")


def _lock_file_exclusive(f):
    """Try to take a non-blocking exclusive lock on file object f. Returns
    True if acquired, False if some other process already holds it."""
    if is_windows():
        import msvcrt
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    else:
        import fcntl
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False


def notify_running_instance():
    """If another instance already holds the lock, ask it to show its
    window and return True (caller should exit immediately after)."""
    lock_path = _instance_lock_path()
    if not os.path.exists(lock_path):
        return False
    try:
        with open(lock_path, "r") as f:
            info = json.load(f)
        port, token = int(info["port"]), info["token"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False  # no running instance has published its info (yet, or anymore)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(("127.0.0.1", port))
        s.sendall(f"SHOW {token}\n".encode("utf-8"))
        s.close()
        return True
    except OSError:
        return False


def acquire_single_instance_lock(on_show):
    """Takes the exclusive lock file, starts a background TCP server on an
    OS-assigned port, and publishes {port, token} in the lock file for
    later launches to find via notify_running_instance(). Calls on_show()
    whenever a request with the correct token comes in. Returns an opaque
    handle -- keep a reference for the app's lifetime and close it on quit
    via release_single_instance_lock(). Returns None if another instance
    already holds the lock (shouldn't normally happen here, since
    notify_running_instance() is checked first in __main__, but handled
    defensively in case of a race) or if a listening socket couldn't be
    opened at all; in that case we simply proceed without the lock rather
    than blocking startup."""
    os.makedirs(app_config_dir(), exist_ok=True)
    lock_path = _instance_lock_path()

    # Opened with "a+" (not "w") so acquiring the lock never truncates a
    # file another process might currently be reading from in
    # notify_running_instance(); we truncate ourselves only after we know
    # we hold the lock. Kept open for the app's whole lifetime.
    lock_file = open(lock_path, "a+")
    if not _lock_file_exclusive(lock_file):
        lock_file.close()
        return None

    if not is_windows():
        try:
            os.chmod(lock_path, 0o600)
        except OSError:
            pass

    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))  # OS picks a free ephemeral port
        srv.listen(5)
        port = srv.getsockname()[1]
    except OSError:
        lock_file.close()
        return None

    token = secrets.token_hex(16)
    lock_file.seek(0)
    lock_file.truncate()
    json.dump({"port": port, "token": token}, lock_file)
    lock_file.flush()

    def _serve():
        expected = f"SHOW {token}".encode("utf-8")
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return  # socket was closed (app shutting down)
            try:
                data = conn.recv(256)
            except OSError:
                data = b""
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
            if data.strip() == expected:
                on_show()

    threading.Thread(target=_serve, daemon=True).start()
    return (srv, lock_file)


def release_single_instance_lock(handle):
    """Closes the listening socket and the lock file (which also releases
    the OS-level file lock), and best-effort removes the lock file so a
    dead port/token isn't left around for the next launch to trip over --
    though notify_running_instance() already handles a stale file safely
    (a refused connection just means "no running instance", same as if
    the file didn't exist)."""
    if not handle:
        return
    srv, lock_file = handle
    try:
        srv.close()
    except OSError:
        pass
    try:
        lock_file.close()
    except OSError:
        pass
    try:
        os.remove(_instance_lock_path())
    except OSError:
        pass


# ---------------------------------------------------------------------------

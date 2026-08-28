# Updating Server Control Suite

The Linux and Windows variants have independent versions.

## Before updating

1. Back up configuration.
2. Read `CHANGELOG.md`.
3. Check whether environment variables or requirements changed.
4. Keep a copy of the last known working script.

## Git clone installation

```bash
git pull
```

Then restart the correct platform build.

### Linux systemd

```bash
sudo systemctl restart server-control
sudo systemctl status server-control
```

### Linux manual

Stop the existing process and run:

```bash
source .venv/bin/activate
python3 server_control_linux.py
```

### Windows

```powershell
git pull
py server_control_win.py
```

The Windows application compares the running source with its stable installed copy and can update the installed copy during a normal launch.

## Manual release-file update

If you downloaded only a `.py` release asset:

1. Download the new platform file.
2. Back up the current file.
3. Replace the old source file.
4. Restart Server Control.
5. Confirm Telegram and the web dashboard work.

## Version update checklist for maintainers

For a Linux update:

```text
server_control_linux.py
VERSIONS.md
CHANGELOG.md
README.md / README.id.md when features change
requirements-linux.txt when dependencies change
docs when setup/config changes
```

Tag:

```text
linux-vX.Y.Z
```

For a Windows update:

```text
server_control_win.py
VERSIONS.md
CHANGELOG.md
README.md / README.id.md when features change
requirements-windows.txt when dependencies change
docs when setup/config changes
```

Tag:

```text
windows-vX.Y.Z
```

Never overwrite an old release tag with a different build.

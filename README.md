# Server Control Suite

<p align="center">
  <strong>Remote server and PC management through a Telegram bot + web dashboard.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Linux-v4.0.0-111827?style=flat-square&logo=linux&logoColor=white" alt="Linux v4.0.0">
  <img src="https://img.shields.io/badge/Windows-v5.0.0-0078D4?style=flat-square&logo=windows11&logoColor=white" alt="Windows v5.0.0">
  <img src="https://img.shields.io/badge/Python-3.8%2B%20Linux%20%7C%203.10%2B%20Windows-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Telegram-Bot-26A5E4?style=flat-square&logo=telegram&logoColor=white" alt="Telegram">
  <img src="https://img.shields.io/badge/Web-Flask-111827?style=flat-square&logo=flask&logoColor=white" alt="Flask">
</p>

<p align="center">
  <a href="./README.id.md">Bahasa Indonesia</a>
  ·
  <a href="./docs/INSTALL_LINUX.md">Linux Install</a>
  ·
  <a href="./docs/INSTALL_WINDOWS.md">Windows Install</a>
  ·
  <a href="./SECURITY.md">Security</a>
</p>

---

## Overview

**Server Control Suite** contains two single-file remote administration applications:

| Platform | File | Version | Runtime |
|---|---|---:|---|
| Linux | `server_control_linux.py` | 4.0.0 | Python 3.8+ |
| Windows | `server_control_win.py` | 5.0.0 | Python 3.10+ |

Both variants combine a private Telegram control bot with a browser-based dashboard for system monitoring and administration.

The Linux build includes a live dashboard, network monitoring, `systemctl` service management, log viewing, file editing, Telegram resource alerts, terminal commands, process management, Docker controls, firewall/iptables controls, and script management.

The Windows build is a separate Windows-native implementation with automatic dependency setup, a first-run configuration wizard, Windows Services, Event Viewer integration, Task Scheduler startup, Windows Defender Firewall integration, hidden/background execution, and dashboard shortcuts.

> [!IMPORTANT]
> This is a **powerful remote-administration tool**. It can execute commands, edit files, control processes/services, and change firewall or scheduled-task configuration. Do not expose the web dashboard directly to the public Internet without additional access controls.

## Features

### Shared capabilities

- Telegram bot restricted to the configured owner/admin ID
- Web dashboard with token authentication
- CPU, RAM, disk, network, uptime, and process monitoring
- File manager
- Upload/download and file editing
- Process management
- Python/script discovery and execution
- Web terminal
- Docker management
- Resource alerts sent to Telegram
- Configurable dashboard port
- Responsive browser UI

### Linux

- `systemctl` service manager
- journal/syslog/auth/dmesg log tools
- iptables controls
- cron management
- nohup-based script runner
- Linux network and storage tools
- Oracle Cloud deployment use case

### Windows

- Windows Services manager
- Event Viewer integration
- Windows Defender Firewall controls
- Scheduled Tasks management
- automatic Task Scheduler startup registration
- hidden background process through `pythonw.exe`
- automatic dashboard shortcut creation
- local application data/config directory
- Waitress production WSGI server
- single-instance protection

## Security Model

Telegram actions use an owner-ID check before sensitive handlers execute.

The dashboard is protected by an access token. The Windows build additionally includes per-IP login rate limiting and constant-time token comparison.

For production use:

- use a long, random `DASH_TOKEN`;
- use a separate long `DASH_SECRET`;
- never commit a Telegram bot token;
- prefer Tailscale/WireGuard/VPN, Cloudflare Access, or a TLS reverse proxy;
- restrict inbound firewall rules to trusted sources;
- do not expose port `8080` openly to the Internet.

See [Security Hardening](./docs/SECURITY_HARDENING.md).

## Get the Project

### Option 1 — Git clone

```bash
git clone https://github.com/baska-pro/server-control-suite.git
cd server-control-suite
```

To update later:

```bash
git pull
```

### Option 2 — Download ZIP

On GitHub:

```text
Code → Download ZIP
```

Extract the archive and choose the script for your operating system.

### Option 3 — GitHub Release

When releases are published, download only the platform file you need from the latest release:

```text
server_control_linux.py
server_control_win.py
```

## Quick Start — Linux

```bash
git clone https://github.com/baska-pro/server-control-suite.git
cd server-control-suite

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-linux.txt

cp .env.example .env
nano .env
```

Load the environment and run:

```bash
set -a
source .env
set +a

python3 server_control_linux.py
```

Required configuration:

```text
TOKEN_SERVER_CONTROL
ADMIN_ID
```

The Linux source reads `TOKEN_SERVER_CONTROL`, `ADMIN_ID`, `DASH_PORT`, dashboard secrets/tokens, and alert thresholds from environment variables.

For persistent startup with `systemd`, follow [Linux Installation](./docs/INSTALL_LINUX.md).

## Quick Start — Windows

Requirements:

```text
Windows 10 / 11
Python 3.10+
Internet access during first dependency installation
```

Clone or download the repo, then open **PowerShell / Terminal as Administrator**:

```powershell
py server_control_win.py
```

On first run the Windows build:

1. requests Administrator elevation when available;
2. asks for Telegram Bot Token;
3. asks for the Telegram Owner/Admin ID;
4. asks for the dashboard port;
5. stores configuration under the current user's application-data directory;
6. creates/updates its stable installed copy;
7. creates a Task Scheduler startup task;
8. creates Dashboard shortcuts;
9. creates a private-profile Windows Firewall rule when elevated;
10. launches the control suite in the background without keeping a terminal open.

The first-run wizard and saved configuration behavior are implemented directly in the Windows source. The startup/background workflow uses Task Scheduler and the installed application copy.

Full instructions: [Windows Installation](./docs/INSTALL_WINDOWS.md).

## Default Dashboard

Default port:

```text
8080
```

Typical local URLs:

```text
http://127.0.0.1:8080
http://SERVER_LAN_IP:8080
```

If the preferred port is already occupied, both applications can search for a nearby free port.

## Configuration

Important settings:

| Setting | Linux | Windows | Purpose |
|---|---:|---:|---|
| `TOKEN_SERVER_CONTROL` | Required | Optional env override | Telegram bot token |
| `ADMIN_ID` | Required | Optional env override | Allowed Telegram owner ID |
| `DASH_PORT` | Optional | Optional | Dashboard port |
| `DASH_SECRET` | Strongly recommended | Optional override | Flask session secret |
| `DASH_TOKEN` | Strongly recommended | Optional override | Dashboard login token |
| `ALERT_CPU` | Optional | Optional | CPU alert threshold |
| `ALERT_RAM` | Optional | Optional | RAM alert threshold |
| `ALERT_DISK` | Optional | Optional | Disk alert threshold |
| `ALERT_CD` | Optional | Optional | Alert cooldown seconds |

See [Configuration](./docs/CONFIGURATION.md).

## Updating

For a cloned installation:

```bash
git pull
```

Then restart the application.

The Windows build keeps a stable installed copy and refreshes it when the source file changes during a normal run. The Linux build should be restarted through your process manager/systemd after pulling updates.

See [Updating](./docs/UPDATE.md).

## Repository Structure

```text
server-control-suite/
├── server_control_linux.py
├── server_control_win.py
├── requirements-linux.txt
├── requirements-windows.txt
├── .env.example
├── README.md
├── README.id.md
├── CHANGELOG.md
├── SECURITY.md
├── CONTRIBUTING.md
├── VERSIONS.md
├── LICENSE
├── docs/
├── install/
├── assets/
└── .github/
```

## Screenshots

Place application screenshots in:

```text
assets/screenshots/
```

Recommended names:

```text
linux-dashboard.png
linux-telegram.png
windows-dashboard.png
windows-telegram.png
windows-setup.png
```

## Releases and Versioning

Because the two implementations currently have different application versions, use platform-qualified release tags:

```text
linux-v4.0.0
windows-v5.0.0
```

If a release contains both builds, its notes should clearly state the version of each platform.

See [Release Checklist](./docs/RELEASE_CHECKLIST.md).

## License

Copyright © 2026 Lathif Baska.

This repository is published under an **All Rights Reserved** source-available license. See [LICENSE](./LICENSE).

## Author

**Lathif Baska**

GitHub: [@baska-pro](https://github.com/baska-pro)

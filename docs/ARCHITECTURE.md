# Architecture

## Repository

Server Control Suite maintains two platform-specific single-file applications.

```text
Telegram
   │
   ├──── owner-only command handlers
   │
Server Control Core
   │
   ├──── system/process/file/service controls
   ├──── resource history + alerts
   ├──── platform tools
   │
   └──── Flask/Waitress dashboard
             │
             └──── token-authenticated browser
```

## Linux build

Primary components:

- Python Telegram polling application
- Flask development server
- `psutil` system information
- filesystem/script management
- nohup process runner
- systemctl
- Docker CLI
- iptables
- cron
- Linux log commands
- background history and alert threads

## Windows build

Primary components:

- Python Telegram polling application
- Flask served by Waitress
- `psutil` system information
- Windows Services / Event Log tooling
- Task Scheduler
- Windows Defender Firewall
- hidden/background process launching
- stable installed copy under application data
- single-instance mutex
- dashboard Desktop/Start Menu shortcuts
- background history and alert threads

## Trust boundary

Both the Telegram owner and authenticated web user are effectively administrators of the host within the capabilities granted to the process account.

This is why dashboard exposure and credential management are core security concerns rather than optional deployment details.

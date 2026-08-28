# Install on Windows

## Requirements

- Windows 10 or Windows 11
- Python 3.10+
- Internet access for first dependency installation
- Telegram bot token
- Numeric Telegram Owner/Admin ID

## 1. Install Python

Install Python 3.10+ and make sure `py` or `python` works:

```powershell
py --version
```

## 2. Get the repository

With Git:

```powershell
git clone https://github.com/baska-pro/server-control-suite.git
cd server-control-suite
```

Or use:

```text
GitHub → Code → Download ZIP
```

and extract the archive.

## 3. First run

Open PowerShell / Terminal as Administrator and run:

```powershell
py server_control_win.py
```

The application can automatically install missing Python packages.

The setup wizard asks for:

```text
Telegram Bot Token
Telegram Owner/Admin ID
Dashboard port
```

## 4. What the Windows setup does

The application stores runtime data under the current user's application-data location in:

```text
WindowsControlSuite
```

It maintains files such as:

```text
config.json
managed_tasks.json
server_control.py
server_control.log
script_logs/
```

It also attempts to:

- create/update the stable installed copy;
- create a Task Scheduler task named `Windows Control Suite`;
- use `pythonw.exe` for hidden/background execution;
- create Dashboard shortcuts on Desktop and Start Menu;
- add a Windows Defender Firewall rule for the dashboard on the Private profile when elevated.

## 5. Open the dashboard

Typical addresses:

```text
http://127.0.0.1:8080
http://PC-LAN-IP:8080
```

The actual port can differ if the configured port is already occupied.

Use the dashboard access token printed during initial setup or available to the Telegram owner through the bot.

## Commands

Normal setup/run:

```powershell
py server_control_win.py
```

Foreground troubleshooting:

```powershell
py server_control_win.py --foreground
```

Force setup again:

```powershell
py server_control_win.py --setup
```

Reinstall startup task:

```powershell
py server_control_win.py --reinstall-task
```

Remove the startup task:

```powershell
py server_control_win.py --uninstall-task
```

## Update

If cloned with Git:

```powershell
git pull
py server_control_win.py
```

A normal run can refresh the installed copy when the repository source is newer/different.

## Uninstall

1. Remove Task Scheduler registration:

```powershell
py server_control_win.py --uninstall-task
```

2. Stop any running Server Control process.
3. Remove the `WindowsControlSuite` application-data folder if you no longer need configuration/logs.
4. Remove the dashboard firewall rule if it is no longer needed.
5. Delete Desktop/Start Menu dashboard shortcuts if still present.

Back up `config.json` first if you may reinstall later.

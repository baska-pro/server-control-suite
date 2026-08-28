# Configuration

## Linux

Linux primarily uses environment variables.

| Variable | Default | Description |
|---|---:|---|
| `TOKEN_SERVER_CONTROL` | empty | Telegram bot token; required |
| `ADMIN_ID` | `0` | Numeric Telegram owner ID; required |
| `DASH_PORT` | `8080` | Preferred web port |
| `DASH_SECRET` | derived fallback | Flask session signing secret |
| `DASH_TOKEN` | derived fallback | Dashboard login token |
| `ALERT_CPU` | `90` | CPU alert percentage |
| `ALERT_RAM` | `90` | RAM alert percentage |
| `ALERT_DISK` | `95` | Disk alert percentage |
| `ALERT_CD` | `600` | Alert cooldown seconds |

For public/production use, explicitly set random `DASH_SECRET` and `DASH_TOKEN` rather than relying on fallback values.

The Linux program does **not** automatically parse `.env`; load it into the shell or use `EnvironmentFile=` with systemd.

## Windows

Windows supports environment-variable overrides but normally uses its first-run setup and saved configuration.

Config location:

```text
%LOCALAPPDATA%\WindowsControlSuite\config.json
```

or the application-data fallback chosen by the source.

Saved fields include:

```text
telegram_token
admin_id
web_port
web_host
secret_key
dash_token
alert_cpu
alert_ram
alert_disk
alert_cooldown
version
```

Treat `config.json` as sensitive.

## Generate secrets

Linux/macOS:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Windows PowerShell:

```powershell
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

Generate separate values for `DASH_SECRET` and `DASH_TOKEN`.

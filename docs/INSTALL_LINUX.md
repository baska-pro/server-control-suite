# Install on Linux

## Requirements

- Linux server/desktop
- Python 3.8+
- Internet access for dependency installation
- A Telegram bot token
- Your numeric Telegram user ID

Some administrative features require privileges that the service account may not have by default.

## 1. Clone

```bash
git clone https://github.com/baska-pro/server-control-suite.git
cd server-control-suite
```

## 2. Virtual environment

Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

Create the environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-linux.txt
```

The source also contains an automatic dependency installer, but a virtual environment with an explicit requirements file is recommended for a public installation.

## 3. Configure

```bash
cp .env.example .env
nano .env
```

Minimum:

```dotenv
TOKEN_SERVER_CONTROL=YOUR_TELEGRAM_BOT_TOKEN
ADMIN_ID=YOUR_NUMERIC_TELEGRAM_ID
```

Recommended:

```dotenv
DASH_PORT=8080
DASH_SECRET=GENERATE_A_LONG_RANDOM_VALUE
DASH_TOKEN=GENERATE_A_DIFFERENT_LONG_RANDOM_VALUE
```

Generate random secrets:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Load the file:

```bash
set -a
source .env
set +a
```

## 4. Run manually

```bash
python3 server_control_linux.py
```

## 5. Persistent systemd service

Recommended production layout:

```text
/opt/server-control-suite
/etc/server-control-suite/server-control.env
```

Example:

```bash
sudo mkdir -p /opt/server-control-suite
sudo cp -a . /opt/server-control-suite/
sudo mkdir -p /etc/server-control-suite
sudo cp install/linux/server-control.env.example /etc/server-control-suite/server-control.env
sudo nano /etc/server-control-suite/server-control.env
```

Protect secrets:

```bash
sudo chmod 600 /etc/server-control-suite/server-control.env
```

Copy and edit the systemd template:

```bash
sudo cp install/linux/server-control.service.example /etc/systemd/system/server-control.service
sudo nano /etc/systemd/system/server-control.service
```

Replace:

```text
YOUR_LINUX_USER
```

with the Linux account that should run Server Control.

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now server-control
sudo systemctl status server-control
```

Logs:

```bash
journalctl -u server-control -f
```

Restart:

```bash
sudo systemctl restart server-control
```

Stop:

```bash
sudo systemctl stop server-control
```

Disable:

```bash
sudo systemctl disable --now server-control
```

## Firewall

Do not blindly expose the dashboard to the entire Internet.

If LAN/VPN access is required, allow the port only from a trusted network when possible.

Example using UFW:

```bash
sudo ufw allow from 10.0.0.0/8 to any port 8080 proto tcp
```

Adjust the source network for your environment.

## Oracle Cloud

Opening a port can require both:

1. Oracle Cloud Security List / Network Security Group rule.
2. Guest OS firewall rule.

Prefer a private overlay network such as Tailscale instead of a public dashboard port.

## Update

```bash
cd /opt/server-control-suite
sudo git pull
sudo systemctl restart server-control
```

If `/opt/server-control-suite` is not a Git clone, replace the source file manually and restart the service.

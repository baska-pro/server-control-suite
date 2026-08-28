# Security Hardening

Server Control Suite is an administrative tool, not a public web application.

## Critical rule

**Do not expose the dashboard directly to the public Internet unless you have deliberately added a trusted security layer.**

The application can execute commands, modify files, stop processes, manage services/tasks, and modify firewall-related configuration.

## Recommended network models

Best:

```text
Browser → Tailscale/WireGuard/VPN → Server Control
```

Also suitable:

```text
Browser → HTTPS reverse proxy + strong access control → Server Control
```

For Cloudflare deployments, use authenticated Cloudflare Access rather than an unauthenticated public tunnel.

## Dashboard token

Use a long random token:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Do not reuse:

- Telegram bot token;
- password;
- GitHub token;
- API key.

## Flask secret

Set a separate long random `DASH_SECRET`.

## Telegram

- create a dedicated bot;
- restrict the bot with `ADMIN_ID`;
- never post the token in Issues, screenshots, logs, README, or source;
- rotate the bot token immediately if it is exposed.

## Firewall

Prefer allowlisting trusted source networks.

Avoid:

```text
0.0.0.0/0 → dashboard port
```

when the dashboard is reachable from the Internet.

## Privileges

Run with the minimum host privileges needed.

Some features will only work with Administrator/root-equivalent access. Giving the process full privileges means a compromised dashboard account can potentially control the entire machine.

## Backups and screenshots

Before publishing:

- redact tokens;
- redact dashboard URLs when they reveal a sensitive public endpoint;
- redact private file paths if needed;
- inspect config exports;
- inspect terminal output;
- inspect Telegram screenshots.

## Source review

The repository intentionally keeps source readable. Review changes before updating an administrative installation.

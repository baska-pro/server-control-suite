# Security Policy

## Scope

Server Control Suite is a high-privilege remote administration application.

Security issues involving authentication bypass, arbitrary access by an unauthenticated user, credential exposure, path traversal, unsafe file handling, or privilege escalation should be treated as sensitive.

## Reporting

Do not publish exploitable vulnerability details, real dashboard tokens, Telegram bot tokens, private configuration, or production endpoints in a public Issue.

Use GitHub private vulnerability reporting / Security Advisories when available.

Maintainer:

https://github.com/baska-pro

## Supported versions

| Platform | Version |
|---|---|
| Linux | latest `4.x` public release |
| Windows | latest `5.x` public release |

Older builds receive best-effort support.

## Operational Security

Read:

```text
docs/SECURITY_HARDENING.md
```

before exposing a dashboard beyond localhost or a private trusted network.

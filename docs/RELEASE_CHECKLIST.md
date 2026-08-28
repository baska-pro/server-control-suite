# Release Checklist

## Common

- [ ] Source compiles.
- [ ] No token/API key/password is committed.
- [ ] Changelog updated.
- [ ] Version documentation updated.
- [ ] README feature list still matches the application.
- [ ] Install guide still works.
- [ ] Security notes reviewed.
- [ ] Screenshots contain no secrets.
- [ ] Release asset is the same file that was tested.

## Linux

- [ ] Telegram `/start` works.
- [ ] Dashboard login works.
- [ ] File Manager tested.
- [ ] Process/script controls tested.
- [ ] systemctl behavior tested.
- [ ] Docker behavior tested when Docker is available.
- [ ] Firewall/iptables behavior reviewed.
- [ ] systemd restart tested.
- [ ] Tag `linux-vX.Y.Z`.

## Windows

- [ ] First-run setup tested.
- [ ] UAC/elevation flow tested.
- [ ] Task Scheduler startup tested.
- [ ] Hidden/background launch tested.
- [ ] Dashboard shortcut tested.
- [ ] Firewall rule tested.
- [ ] Telegram bot tested.
- [ ] Dashboard login tested.
- [ ] Windows Services/Event Viewer behavior tested.
- [ ] Tag `windows-vX.Y.Z`.

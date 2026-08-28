# Contributing

## Reports

Useful reports include:

- operating system and version;
- Python version;
- Server Control platform/version;
- reproduction steps;
- expected behavior;
- actual behavior;
- redacted logs;
- screenshots with all secrets removed.

## Pull Requests

Before submitting a patch:

1. Keep Linux and Windows behavior clearly separated when platform-specific.
2. Do not commit tokens, config files, credentials, machine-specific secrets, or production URLs.
3. Preserve owner-only authentication for Telegram controls.
4. Preserve dashboard authentication for protected routes.
5. Document new environment variables.
6. Update the appropriate requirements file.
7. Update `CHANGELOG.md` for user-visible changes.
8. Test the affected platform.

## License

By contributing, you confirm you have the right to submit the code and grant the repository owner permission to use and distribute the contribution as part of this project.

# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in FulMen Agent Network, please report it responsibly.

**Email:** Send details to the maintainers via [GitHub Issues](https://github.com/mateable/FulmenAgent/issues) with the label `security`.

If the vulnerability is sensitive (e.g., exposes API keys, allows remote code execution), please **do not** open a public issue. Instead, use [GitHub Private Vulnerability Reporting](https://github.com/mateable/FulmenAgent/security/advisories/new).

## What to Include

- Description of the vulnerability
- Steps to reproduce
- Affected files or components
- Suggested fix (if you have one)

## Security Considerations

FulMen Agent Network runs AI agents that can execute tools, including shell commands and file operations. Keep the following in mind:

### API Keys & Secrets
- Never commit your `.env` file — it contains API keys
- The `.gitignore` already excludes `.env`
- Use `.env.example` as a template (no real keys)
- The dashboard masks all API keys in the Admin Settings UI

### Execution Modes
- **Safe mode** — Agents require user approval before running dangerous tools
- **Unrestricted mode** — Agents run all tools without approval. Only use this in trusted environments

### Network Exposure
- The hub runs on `0.0.0.0:5000` by default — this is accessible on your local network
- Do not expose the hub to the public internet without authentication
- Twilio webhooks require a public URL — use a reverse proxy with HTTPS

### Plugin Security
- Only install plugins from sources you trust
- Plugins can execute arbitrary code through their tools
- Review plugin `tools.py` before enabling

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest on `develop` | Yes |
| Older commits | No |

We recommend always running the latest version. Use the dashboard's built-in updater to stay current.

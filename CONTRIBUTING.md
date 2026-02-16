# Contributing to FulMen Agent Network

Thanks for your interest in contributing! Here's how to get started.

## Getting Started

1. Fork the repo
2. Clone your fork:
   ```bash
   git clone https://github.com/mateable/FulmenAgent.git
   cd FulmenAgent
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the environment template:
   ```bash
   cp ../.env.example ../.env
   ```
5. Start the hub:
   ```bash
   python hub.py
   ```

## Making Changes

1. Create a branch from `develop`:
   ```bash
   git checkout -b your-feature-name develop
   ```
2. Make your changes
3. Test that the hub starts and your changes work
4. Commit with a clear message:
   ```bash
   git commit -m "Add your feature description"
   ```
5. Push to your fork:
   ```bash
   git push origin your-feature-name
   ```
6. Open a Pull Request against the `develop` branch

## What Can You Contribute?

- **New plugins** — Add a folder in `plugins/` with a `manifest.json`, `requirements.txt`, and `tools.py`
- **New connectors** — Discord, Telegram, LINE, WhatsApp, or your own
- **New LLM providers** — Follow the pattern in `src/planner.py`
- **Bug fixes** — Check the Issues tab
- **Documentation** — Improvements to docs in `docs/`
- **Dashboard improvements** — UI/UX changes to `templates/dashboard.html`

## Plugin Structure

To add a new plugin, create a folder in `plugins/`:

```
plugins/your_plugin/
├── manifest.json       # Name, version, description, entry_point
├── requirements.txt    # Any pip dependencies (can be empty)
└── tools.py            # Tool classes + get_tools() function
```

See existing plugins (`my_weather_plugin`, `exa_search_plugin`, `gibberlink_plugin`, `beads_plugin`) for examples.

## Guidelines

- Keep PRs focused — one feature or fix per PR
- Follow existing code patterns and naming conventions
- Don't commit `.env` files or API keys
- Test your changes before submitting

## Questions?

Open an issue on the repo and we'll help you out.

"""Unified configuration for gw-cli."""

import yaml
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "gw-cli"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

# Auto-migrate from email-cli config
OLD_CONFIG_FILE = Path.home() / ".config" / "email-cli" / "config.yaml"

DEFAULT_ACCOUNT = None

DEFAULT_CALENDAR_ALIASES = {}

DEFAULT_TIMEZONE = "America/New_York"


def get_config() -> dict:
    """Load config file, auto-migrating from email-cli if needed."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return yaml.safe_load(f) or {}

    # Auto-migrate from email-cli config
    if OLD_CONFIG_FILE.exists():
        with open(OLD_CONFIG_FILE) as f:
            config = yaml.safe_load(f) or {}
        save_config(config)
        return config

    return {}


def save_config(config: dict) -> None:
    """Save config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f)


def get_account(ctx_account: str | None) -> str:
    """Get account from flag, config alias, or default."""
    config = get_config()
    if ctx_account:
        return config.get("aliases", {}).get(ctx_account, ctx_account)
    account = config.get("default_account", DEFAULT_ACCOUNT)
    if not account:
        raise ValueError("No account specified. Use -a flag or set default_account in ~/.config/gw-cli/config.yaml")
    return account


def get_calendar_aliases() -> dict[str, str]:
    """Get calendar aliases from config, falling back to defaults."""
    config = get_config()
    return config.get("calendar_aliases", DEFAULT_CALENDAR_ALIASES)


def get_timezone() -> str:
    """Get timezone from config, falling back to default."""
    config = get_config()
    return config.get("timezone", DEFAULT_TIMEZONE)

"""Provider configuration for OpenAI-compatible APIs."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 30.0
DEFAULT_CHAT_TIMEOUT_SECONDS = 60.0
PROVIDER_CONFIG_PATH_ENV = "ONCALL_PROVIDER_CONFIG_PATH"

load_dotenv()


@dataclass(frozen=True)
class ProviderConfig:
    """Runtime settings for an OpenAI-compatible provider."""

    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS


def embedding_config_from_env() -> ProviderConfig:
    """Load SiliconFlow embedding settings from environment variables."""
    return ProviderConfig(
        base_url=os.getenv("ONCALL_EMBEDDING_BASE_URL", SILICONFLOW_BASE_URL),
        api_key=os.getenv("ONCALL_EMBEDDING_API_KEY", ""),
        model=os.getenv("ONCALL_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
    )


def chat_config_from_env() -> ProviderConfig:
    """Load Chat Completions settings from environment variables."""
    saved = load_saved_chat_config()
    return ProviderConfig(
        base_url=_first_non_empty(
            saved.get("base_url"),
            os.getenv("ONCALL_CHAT_BASE_URL"),
            os.getenv("OPENAI_BASE_URL"),
        ),
        api_key=_first_non_empty(
            saved.get("api_key"),
            os.getenv("ONCALL_CHAT_API_KEY"),
            os.getenv("OPENAI_API_KEY"),
        ),
        model=_first_non_empty(
            saved.get("model"),
            os.getenv("ONCALL_CHAT_MODEL"),
            os.getenv("OPENAI_MODEL"),
        ),
        timeout_seconds=_timeout_from_env(
            "ONCALL_CHAT_TIMEOUT_SECONDS",
            DEFAULT_CHAT_TIMEOUT_SECONDS,
        ),
    )


def chat_config_file_path() -> Path:
    """Return the user-writable chat-provider config path."""
    configured = os.getenv(PROVIDER_CONFIG_PATH_ENV)
    if configured:
        return Path(configured)
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "InterviewAgent" / "provider-config.json"
    return Path.cwd() / ".cache" / "provider-config.json"


def load_saved_chat_config() -> dict[str, str]:
    """Read locally persisted chat-provider settings without raising on corruption."""
    path = chat_config_file_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        key: str(value).strip()
        for key, value in raw.items()
        if key in {"base_url", "api_key", "model"} and isinstance(value, str)
    }


def save_chat_config(
    *,
    base_url: str,
    model: str,
    api_key: str | None = None,
    clear_api_key: bool = False,
) -> None:
    """Persist local chat-provider settings for packaged desktop runs."""
    existing = load_saved_chat_config()
    data = {
        "base_url": base_url.strip(),
        "model": model.strip(),
        "api_key": "",
    }
    if clear_api_key:
        data["api_key"] = ""
    elif api_key is not None and api_key.strip():
        data["api_key"] = api_key.strip()
    else:
        data["api_key"] = existing.get("api_key", "")

    path = chat_config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _timeout_from_env(name: str, default: float) -> float:
    """Read a positive timeout value from the environment."""
    try:
        timeout = float(os.getenv(name, ""))
    except ValueError:
        return default
    if timeout <= 0:
        return default
    return timeout

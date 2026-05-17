"""Desktop sidecar entrypoint for the packaged interview product."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DesktopSidecarConfig:
    """Runtime configuration passed by the desktop shell."""

    host: str
    port: int
    store_path: Path
    memory_store_path: Path
    profile_root: Path
    ready_file: Path | None
    log_path: Path


def parse_args(argv: Sequence[str]) -> DesktopSidecarConfig:
    """Parse desktop sidecar CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--store-path", default="")
    parser.add_argument("--memory-store-path", default="")
    parser.add_argument("--profile-root", default="")
    parser.add_argument("--ready-file", default="")
    args = parser.parse_args(list(argv))

    data_root = _desktop_data_root()
    return DesktopSidecarConfig(
        host=args.host,
        port=args.port,
        store_path=Path(args.store_path) if args.store_path else data_root / "interview.sqlite3",
        memory_store_path=(
            Path(args.memory_store_path) if args.memory_store_path else data_root / "memory.sqlite3"
        ),
        profile_root=Path(args.profile_root) if args.profile_root else data_root / "browser_profiles",
        ready_file=Path(args.ready_file) if args.ready_file else None,
        log_path=data_root / "sidecar.log",
    )


def configure_desktop_environment(config: DesktopSidecarConfig) -> None:
    """Configure environment variables consumed by the FastAPI runtime."""
    config.store_path.parent.mkdir(parents=True, exist_ok=True)
    config.memory_store_path.parent.mkdir(parents=True, exist_ok=True)
    config.profile_root.mkdir(parents=True, exist_ok=True)
    os.environ["INTERVIEW_STORE_PATH"] = str(config.store_path)
    os.environ["INTERVIEW_MEMORY_STORE_PATH"] = str(config.memory_store_path)
    os.environ["INTERVIEW_BROWSER_PROFILE_DIR"] = str(config.profile_root)
    provider_config_path = config.store_path.parent / "provider-config.json"
    _migrate_legacy_provider_config(provider_config_path)
    os.environ.setdefault("ONCALL_PROVIDER_CONFIG_PATH", str(provider_config_path))
    os.environ.setdefault("INTERVIEW_ENABLE_BROWSER", "1")


def _migrate_legacy_provider_config(target: Path) -> None:
    """Move dev-side provider config into the Tauri app-data directory when needed."""
    legacy = _desktop_data_root() / "provider-config.json"
    if target == legacy or target.exists() or not legacy.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy, target)


def main(argv: Sequence[str] | None = None) -> int:
    """Start the packaged FastAPI server."""
    config = parse_args(sys.argv[1:] if argv is None else argv)
    configure_desktop_environment(config)
    _ensure_standard_streams(config.log_path)
    if config.ready_file is not None:
        _start_ready_probe(config)

    import uvicorn

    from oncall_app.api.app_factory import create_app

    uvicorn.run(
        create_app(test_mode=False),
        host=config.host,
        port=config.port,
        reload=False,
        access_log=False,
        use_colors=False,
    )
    return 0


def _ensure_standard_streams(log_path: Path) -> None:
    """Attach GUI-packaged stdout/stderr to a local log file before Uvicorn starts."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:
        sys.stdout = log_path.open("a", encoding="utf-8", buffering=1)
    if sys.stderr is None:
        sys.stderr = log_path.open("a", encoding="utf-8", buffering=1)


def _start_ready_probe(config: DesktopSidecarConfig) -> None:
    thread = threading.Thread(
        target=_write_ready_file_after_health,
        args=(config.host, config.port, config.ready_file),
        daemon=True,
        name="desktop-sidecar-ready-probe",
    )
    thread.start()


def _write_ready_file_after_health(host: str, port: int, ready_file: Path | None) -> None:
    if ready_file is None:
        return
    url = f"http://{host}:{port}/health"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    ready_file.parent.mkdir(parents=True, exist_ok=True)
                    ready_file.write_text("ready", encoding="utf-8")
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)


def _desktop_data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "InterviewAgent"
    return Path.cwd() / ".cache" / "desktop"


if __name__ == "__main__":
    raise SystemExit(main())

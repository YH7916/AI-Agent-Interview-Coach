"""Tests for the desktop Python sidecar entrypoint."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from oncall_app.desktop_sidecar import (
    DesktopSidecarConfig,
    _ensure_standard_streams,
    configure_desktop_environment,
    main,
    parse_args,
)


class DesktopSidecarTests(unittest.TestCase):
    """The packaged app should own runtime paths instead of using dev cache paths."""

    def test_parse_args_accepts_explicit_paths(self) -> None:
        config = parse_args(
            [
                "--host",
                "127.0.0.1",
                "--port",
                "9123",
                "--store-path",
                "D:/tmp/interview.sqlite3",
                "--memory-store-path",
                "D:/tmp/memory.sqlite3",
                "--profile-root",
                "D:/tmp/profiles",
                "--ready-file",
                "D:/tmp/ready.txt",
            ]
        )

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 9123)
        self.assertEqual(config.store_path, Path("D:/tmp/interview.sqlite3"))
        self.assertEqual(config.memory_store_path, Path("D:/tmp/memory.sqlite3"))
        self.assertEqual(config.profile_root, Path("D:/tmp/profiles"))
        self.assertEqual(config.ready_file, Path("D:/tmp/ready.txt"))
        self.assertEqual(config.log_path.parts[-2:], ("InterviewAgent", "sidecar.log"))

    def test_default_paths_live_under_local_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": temp_dir}, clear=False):
                config = parse_args(["--port", "9124"])

        self.assertEqual(config.port, 9124)
        self.assertEqual(config.store_path.parts[-2:], ("InterviewAgent", "interview.sqlite3"))
        self.assertEqual(config.memory_store_path.parts[-2:], ("InterviewAgent", "memory.sqlite3"))
        self.assertEqual(config.profile_root.parts[-2:], ("InterviewAgent", "browser_profiles"))

    def test_configure_environment_sets_runtime_paths(self) -> None:
        config = DesktopSidecarConfig(
            host="127.0.0.1",
            port=9001,
            store_path=Path("D:/tmp/interview.sqlite3"),
            memory_store_path=Path("D:/tmp/memory.sqlite3"),
            profile_root=Path("D:/tmp/profiles"),
            ready_file=None,
            log_path=Path("D:/tmp/sidecar.log"),
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            configure_desktop_environment(config)

            self.assertEqual(os.environ["INTERVIEW_STORE_PATH"], "D:\\tmp\\interview.sqlite3")
            self.assertEqual(os.environ["INTERVIEW_MEMORY_STORE_PATH"], "D:\\tmp\\memory.sqlite3")
            self.assertEqual(os.environ["INTERVIEW_BROWSER_PROFILE_DIR"], "D:\\tmp\\profiles")
            self.assertEqual(
                os.environ["ONCALL_PROVIDER_CONFIG_PATH"],
                "D:\\tmp\\provider-config.json",
            )
            self.assertEqual(os.environ["INTERVIEW_ENABLE_BROWSER"], "1")

    def test_configure_environment_migrates_legacy_provider_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_root = Path(temp_dir) / "InterviewAgent"
            legacy_root.mkdir()
            legacy = legacy_root / "provider-config.json"
            legacy.write_text('{"model":"gpt-5.4"}', encoding="utf-8")
            target_root = Path(temp_dir) / "dev.lyh.interview-agent"
            config = DesktopSidecarConfig(
                host="127.0.0.1",
                port=9001,
                store_path=target_root / "interview.sqlite3",
                memory_store_path=target_root / "memory.sqlite3",
                profile_root=target_root / "profiles",
                ready_file=None,
                log_path=target_root / "sidecar.log",
            )

            with mock.patch.dict(os.environ, {"LOCALAPPDATA": temp_dir}, clear=True):
                configure_desktop_environment(config)

            target = target_root / "provider-config.json"
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), legacy.read_text(encoding="utf-8"))

    def test_main_reads_process_arguments_when_packaged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(
                sys,
                "argv",
                [
                    "interview-agent-sidecar.exe",
                    "--port",
                    "9432",
                    "--store-path",
                    str(Path(temp_dir) / "interview.sqlite3"),
                    "--memory-store-path",
                    str(Path(temp_dir) / "memory.sqlite3"),
                    "--profile-root",
                    str(Path(temp_dir) / "profiles"),
                ],
            ):
                with mock.patch("uvicorn.run") as run:
                    self.assertEqual(main(), 0)

        self.assertEqual(run.call_args.kwargs["port"], 9432)
        self.assertFalse(run.call_args.kwargs["use_colors"])

    def test_gui_packaged_process_gets_log_backed_standard_streams(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "sidecar.log"
            original_stdout = sys.stdout
            original_stderr = sys.stderr
            try:
                sys.stdout = None
                sys.stderr = None
                _ensure_standard_streams(log_path)

                self.assertIsNotNone(sys.stdout)
                self.assertIsNotNone(sys.stderr)
                sys.stderr.write("diagnostic\n")
            finally:
                if sys.stdout is not None:
                    sys.stdout.close()
                if sys.stderr is not None:
                    sys.stderr.close()
                sys.stdout = original_stdout
                sys.stderr = original_stderr

            self.assertIn("diagnostic", log_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

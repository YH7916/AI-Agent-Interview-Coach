"""Tests for desktop packaging manifests."""

import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PackagingManifestTests(unittest.TestCase):
    """Desktop manifests should keep Python sidecar packaging explicit."""

    def test_pyinstaller_spec_references_required_assets(self) -> None:
        spec = PROJECT_ROOT / "packaging" / "pyinstaller" / "interview-agent-sidecar.spec"

        text = spec.read_text(encoding="utf-8")

        self.assertIn("oncall_app", text)
        self.assertIn("frontend", text)
        self.assertIn("data", text)
        self.assertIn("desktop_sidecar.py", text)
        self.assertIn("playwright", text)

    def test_tauri_config_declares_sidecar(self) -> None:
        config_path = PROJECT_ROOT / "desktop" / "src-tauri" / "tauri.conf.json"

        config = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(config["productName"], "AI Agent Interview Coach")
        self.assertEqual(config["identifier"], "dev.lyh.interview-agent")
        self.assertEqual(config["build"]["frontendDist"], "../../frontend")
        self.assertIn("binaries/interview-agent-sidecar", config["bundle"]["externalBin"])
        self.assertIn("icons/icon.ico", config["bundle"]["icon"])
        self.assertEqual(
            config["bundle"]["windows"]["nsis"]["installerHooks"],
            "nsis-hooks.nsh",
        )
        self.assertTrue((PROJECT_ROOT / "desktop" / "src-tauri" / "icons" / "icon.ico").is_file())

    def test_release_desktop_app_uses_windows_gui_subsystem(self) -> None:
        main_rs = PROJECT_ROOT / "desktop" / "src-tauri" / "src" / "main.rs"

        text = main_rs.read_text(encoding="utf-8")

        self.assertIn('windows_subsystem = "windows"', text)
        self.assertIn("not(debug_assertions)", text)

    def test_desktop_shell_terminates_sidecar_process_tree(self) -> None:
        main_rs = PROJECT_ROOT / "desktop" / "src-tauri" / "src" / "main.rs"

        text = main_rs.read_text(encoding="utf-8")

        self.assertIn("impl Drop for SidecarState", text)
        self.assertIn("terminate_child_tree", text)
        self.assertIn("start_main_window_watchdog", text)
        self.assertIn('get_webview_window("main").is_none()', text)
        self.assertIn("RunEvent::ExitRequested", text)
        self.assertIn("RunEvent::Exit", text)
        self.assertIn("taskkill", text)
        self.assertIn('"/T"', text)
        self.assertIn("CREATE_NO_WINDOW", text)
        self.assertIn("creation_flags(CREATE_NO_WINDOW)", text)
        self.assertIn("stdout(Stdio::null())", text)

    def test_nsis_installer_kills_locked_processes_before_install(self) -> None:
        hooks = PROJECT_ROOT / "desktop" / "src-tauri" / "nsis-hooks.nsh"

        text = hooks.read_text(encoding="utf-8")

        self.assertIn("NSIS_HOOK_PREINSTALL", text)
        self.assertIn("NSIS_HOOK_PREUNINSTALL", text)
        self.assertIn("taskkill /F /T /IM ai-agent-interview-coach.exe", text)
        self.assertIn("taskkill /F /T /IM interview-agent-sidecar.exe", text)

    def test_tauri_capability_uses_core_defaults_only(self) -> None:
        capability_path = PROJECT_ROOT / "desktop" / "src-tauri" / "capabilities" / "default.json"

        capability = json.loads(capability_path.read_text(encoding="utf-8"))
        permissions = json.dumps(capability.get("permissions", []))

        self.assertIn("core:default", permissions)
        self.assertNotIn("shell:allow-execute", permissions)


if __name__ == "__main__":
    unittest.main()

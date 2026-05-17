#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    net::TcpListener,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::Duration,
};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

struct SidecarState {
    child: Mutex<Option<Child>>,
}

impl SidecarState {
    fn stop(&self) {
        let child = {
            let mut guard = self.child.lock().expect("sidecar lock poisoned");
            guard.take()
        };
        if let Some(child) = child {
            terminate_child_tree(child);
        }
    }
}

impl Drop for SidecarState {
    fn drop(&mut self) {
        if let Ok(child) = self.child.get_mut() {
            if let Some(child) = child.take() {
                terminate_child_tree(child);
            }
        }
    }
}

fn main() {
    let app = tauri::Builder::default()
        .manage(SidecarState {
            child: Mutex::new(None),
        })
        .setup(|app| {
            let port = free_port().expect("failed to pick a local port");
            let app_data_dir = app
                .path()
                .app_local_data_dir()
                .expect("failed to resolve app data dir");
            std::fs::create_dir_all(&app_data_dir)?;

            let sidecar_path = sidecar_path(app)?;
            let store_path = app_data_dir.join("interview.sqlite3");
            let memory_store_path = app_data_dir.join("memory.sqlite3");
            let profile_root = app_data_dir.join("browser_profiles");

            let mut sidecar_command = Command::new(sidecar_path);
            sidecar_command
                .arg("--port")
                .arg(port.to_string())
                .arg("--store-path")
                .arg(store_path)
                .arg("--memory-store-path")
                .arg(memory_store_path)
                .arg("--profile-root")
                .arg(profile_root)
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null());
            #[cfg(windows)]
            sidecar_command.creation_flags(CREATE_NO_WINDOW);
            let child = sidecar_command.spawn()?;

            let state = app.state::<SidecarState>();
            *state.child.lock().expect("sidecar lock poisoned") = Some(child);

            wait_for_health(port);
            let url = format!("http://127.0.0.1:{}/v3", port);
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url.parse()?))
                .title("AI Agent Interview Coach")
                .inner_size(1180.0, 820.0)
                .min_inner_size(960.0, 680.0)
                .build()?;
            start_main_window_watchdog(app.handle().clone());
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(
                event,
                tauri::WindowEvent::CloseRequested { .. } | tauri::WindowEvent::Destroyed
            ) {
                window.state::<SidecarState>().stop();
                window.app_handle().exit(0);
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building desktop app");

    app.run(|app_handle, event| {
        match event {
            tauri::RunEvent::WindowEvent { event, .. }
                if matches!(
                    event,
                    tauri::WindowEvent::CloseRequested { .. } | tauri::WindowEvent::Destroyed
                ) =>
            {
                app_handle.state::<SidecarState>().stop();
                app_handle.exit(0);
            }
            tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit => {
                app_handle.state::<SidecarState>().stop();
            }
            _ => {}
        }
    });
}

fn free_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    Ok(listener.local_addr()?.port())
}

fn wait_for_health(port: u16) {
    for _ in 0..150 {
        if std::net::TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return;
        }
        thread::sleep(Duration::from_millis(200));
    }
}

fn terminate_child_tree(mut child: Child) {
    #[cfg(windows)]
    {
        let pid = child.id().to_string();
        let mut taskkill = Command::new("taskkill");
        taskkill
            .args(["/PID", pid.as_str(), "/T", "/F"])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .creation_flags(CREATE_NO_WINDOW);
        let _ = taskkill.status();
    }

    let _ = child.kill();
    let _ = child.wait();
}

fn start_main_window_watchdog(app_handle: tauri::AppHandle) {
    thread::spawn(move || loop {
        thread::sleep(Duration::from_millis(500));
        if app_handle.get_webview_window("main").is_none() {
            app_handle.state::<SidecarState>().stop();
            app_handle.exit(0);
            break;
        }
    });
}

fn sidecar_path(app: &tauri::App) -> tauri::Result<PathBuf> {
    let resource_dir = app.path().resource_dir()?;
    let name = if cfg!(windows) {
        "interview-agent-sidecar.exe"
    } else {
        "interview-agent-sidecar"
    };
    let current_exe_dir = std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(PathBuf::from));
    let mut candidates = vec![resource_dir.join("binaries").join(name), resource_dir.join(name)];
    if let Some(exe_dir) = current_exe_dir {
        candidates.push(exe_dir.join(name));
    }
    Ok(candidates
        .into_iter()
        .find(|candidate| candidate.exists())
        .unwrap_or_else(|| resource_dir.join(name)))
}

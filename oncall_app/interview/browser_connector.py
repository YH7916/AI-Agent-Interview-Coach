"""Browser fetch connector for user-authorized interview sources."""

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlparse


@dataclass(frozen=True)
class BrowserFetchResult:
    """Result returned by a browser fetch connector."""

    url: str
    final_url: str
    title: str
    html: str
    needs_login: bool
    error: str = ""
    status_code: int = 200
    content_type: str = "text/html"
    login_url: str = ""
    profile_host: str = ""
    login_signals: dict[str, object] | None = None
    interaction_trace: tuple[str, ...] = ()


@dataclass(frozen=True)
class BrowserLoginResult:
    """Result returned after requesting a visible login window."""

    opened: bool
    url: str
    host: str
    profile_dir: str
    message: str
    error: str = ""


class BrowserConnector(Protocol):
    """Fetch pages with a browser profile."""

    def fetch(self, url: str, profile_dir: str | Path) -> BrowserFetchResult:
        """Fetch a page using a browser profile."""

    def open_login(self, url: str, profile_dir: str | Path) -> BrowserLoginResult:
        """Open a visible browser login window for a browser profile."""

    def is_login_open(self, profile_dir: str | Path) -> bool:
        """Return whether a visible login window is currently using this profile."""


class DisabledBrowserConnector:
    """Safe default when browser automation is not enabled."""

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason or "Set INTERVIEW_ENABLE_BROWSER=1 and install Playwright Chromium."

    def fetch(self, url: str, profile_dir: str | Path) -> BrowserFetchResult:
        del profile_dir
        return BrowserFetchResult(
            url=url,
            final_url=url,
            title="",
            html="",
            needs_login=True,
            error=f"Browser connector disabled. {self.reason}",
        )

    def open_login(self, url: str, profile_dir: str | Path) -> BrowserLoginResult:
        """Return a clear disabled response without touching browser state."""
        return BrowserLoginResult(
            opened=False,
            url=url,
            host=_host_from_profile_dir(profile_dir),
            profile_dir=str(profile_dir),
            message="Browser connector disabled.",
            error=self.reason,
        )

    def is_login_open(self, profile_dir: str | Path) -> bool:
        del profile_dir
        return False


class PlaywrightBrowserConnector:
    """Fetch pages through a persistent Chromium profile using visible, user-like browsing."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._login_threads: dict[str, threading.Thread] = {}

    def fetch(self, url: str, profile_dir: str | Path) -> BrowserFetchResult:
        from playwright.sync_api import Error, TimeoutError, sync_playwright

        from oncall_app.interview.web_login import detect_login_wall

        Path(profile_dir).mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=_browser_headless(),
                viewport={"width": 1280, "height": 900},
                channel=_browser_channel(),
                slow_mo=_browser_slow_mo_ms(),
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                except TimeoutError:
                    pass
                trace = _browse_like_user(page)
                html = page.content()
                title = page.title()
                final_url = page.url
                try:
                    probe_text = page.locator("body").inner_text(timeout=3_000)
                except Error:
                    probe_text = html
            finally:
                context.close()
        probe = detect_login_wall(probe_text, final_url)
        return BrowserFetchResult(
            url=url,
            final_url=final_url,
            title=title,
            html=html,
            needs_login=probe.needs_login,
            login_url=final_url if probe.needs_login else "",
            login_signals={
                "state": probe.state,
                "confidence": probe.confidence,
                "indicators": probe.indicators,
                "reason": probe.reason,
            },
            interaction_trace=tuple(trace),
        )

    def fetch_by_click(
        self,
        search_url: str,
        target_url: str,
        profile_dir: str | Path,
    ) -> BrowserFetchResult:
        """Open a search page and navigate to a target detail page by clicking its link."""
        results = self.fetch_result_pages_by_click(search_url, [target_url], profile_dir)
        if results:
            return results[0]
        return BrowserFetchResult(
            url=target_url,
            final_url=search_url,
            title="",
            html="",
            needs_login=False,
            error="未找到可点击详情链接，已跳过该候选，避免把搜索页当详情页入库。",
        )

    def fetch_result_pages_by_click(
        self,
        search_url: str,
        target_urls: list[str],
        profile_dir: str | Path,
    ) -> list[BrowserFetchResult]:
        """Click several detail links from one visible browser session."""
        from playwright.sync_api import Error, TimeoutError, sync_playwright

        from oncall_app.interview.web_login import detect_login_wall

        if not target_urls:
            return []
        Path(profile_dir).mkdir(parents=True, exist_ok=True)
        results: list[BrowserFetchResult] = []
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=_browser_headless(),
                viewport={"width": 1280, "height": 900},
                channel=_browser_channel(),
                slow_mo=_browser_slow_mo_ms(),
            )
            try:
                search_page = context.pages[0] if context.pages else context.new_page()
                search_trace = [f"复用搜索结果：{search_url}"]
                for target_url in target_urls:
                    trace = [
                        *search_trace,
                        f"同浏览器会话打开详情页：{target_url}",
                    ]
                    page = context.new_page() if context.pages else search_page
                    try:
                        page.goto(target_url, wait_until="domcontentloaded", timeout=20_000, referer=search_url)
                    except TimeoutError:
                        trace.append("详情页加载超时，继续读取当前页面")
                    trace.extend(_browse_like_user(page, scrolls=1))
                    html = page.content()
                    title = page.title()
                    final_url = page.url
                    try:
                        probe_text = page.locator("body").inner_text(timeout=3_000)
                    except Error:
                        probe_text = html
                    probe = detect_login_wall(probe_text, final_url)
                    results.append(
                        BrowserFetchResult(
                            url=target_url,
                            final_url=final_url,
                            title=title,
                            html=html,
                            needs_login=probe.needs_login,
                            error="",
                            login_url=final_url if probe.needs_login else "",
                            login_signals={
                                "state": probe.state,
                                "confidence": probe.confidence,
                                "indicators": probe.indicators,
                                "reason": probe.reason,
                            },
                            interaction_trace=tuple(trace),
                        )
                    )
                    if page is not search_page:
                        page.close()
            finally:
                context.close()
        return results

    def open_login(self, url: str, profile_dir: str | Path) -> BrowserLoginResult:
        """Open a visible persistent-profile browser window and return immediately."""
        profile_path = Path(profile_dir)
        profile_path.mkdir(parents=True, exist_ok=True)
        key = str(profile_path.resolve())
        with self._lock:
            active = self._login_threads.get(key)
            if active and active.is_alive():
                return BrowserLoginResult(
                    opened=True,
                    url=url,
                    host=_host_from_profile_dir(profile_path),
                    profile_dir=str(profile_path),
                    message="Login window is already open.",
                )
            thread = threading.Thread(
                target=self._run_login_window,
                args=(key, url, profile_path),
                daemon=True,
                name=f"interview-login-{profile_path.name}",
            )
            self._login_threads[key] = thread
            thread.start()
        return BrowserLoginResult(
            opened=True,
            url=url,
            host=_host_from_profile_dir(profile_path),
            profile_dir=str(profile_path),
            message="Login window opened. Log in manually, then close the browser window.",
        )

    def is_login_open(self, profile_dir: str | Path) -> bool:
        profile_path = Path(profile_dir)
        key = str(profile_path.resolve())
        with self._lock:
            active = self._login_threads.get(key)
            return bool(active and active.is_alive())

    def _run_login_window(self, key: str, url: str, profile_dir: Path) -> None:
        try:
            self._login_window_loop(url, profile_dir)
        finally:
            with self._lock:
                self._login_threads.pop(key, None)

    @staticmethod
    def _login_window_loop(url: str, profile_dir: Path) -> None:
        from playwright.sync_api import Error, TimeoutError, sync_playwright

        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                viewport={"width": 1280, "height": 900},
                channel=_browser_channel(),
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                except TimeoutError:
                    pass
                while context.pages:
                    try:
                        context.pages[0].wait_for_timeout(1_000)
                    except Error:
                        break
            finally:
                context.close()


def _browser_headless() -> bool:
    """Use visible browser windows by default so the collection behaves like user browsing."""
    raw = os.environ.get("INTERVIEW_BROWSER_HEADLESS", "").strip().lower()
    if not raw:
        return False
    return raw in {"1", "true", "yes"}


def _browser_slow_mo_ms() -> int:
    """Optional debugging delay. Production collection should not slow every action."""
    raw = os.environ.get("INTERVIEW_BROWSER_SLOW_MO_MS", "").strip()
    if not raw:
        return 0
    try:
        return max(int(raw), 0)
    except ValueError:
        return 0


def _browser_channel() -> str | None:
    """Return optional Chrome/Edge channel configuration for a more user-like browser."""
    channel = os.environ.get("INTERVIEW_BROWSER_CHANNEL", "").strip()
    if channel:
        return channel
    if os.name == "nt":
        for candidate, paths in {
            "chrome": (
                Path(os.environ.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe",
                Path(os.environ.get("ProgramFiles(x86)", "")) / "Google/Chrome/Application/chrome.exe",
            ),
            "msedge": (
                Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
                Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
            ),
        }.items():
            if any(path.is_file() for path in paths):
                return candidate
    return None


def _host_from_profile_dir(profile_dir: str | Path) -> str:
    """Best-effort host display for connector-level responses."""
    name = Path(profile_dir).name
    if name.startswith("web-fetch-"):
        return name.removeprefix("web-fetch-").replace("-", ".")
    return name


def _browse_like_user(page, scrolls: int = 2) -> list[str]:
    """Let dynamic pages render and expose content through small user-like actions."""
    trace = ["等待页面渲染"]
    page.wait_for_timeout(450)
    try:
        page.mouse.move(420, 360)
        trace.append("移动鼠标")
    except Exception:  # pragma: no cover - browser failures are provider-specific.
        pass
    for index in range(scrolls):
        try:
            page.mouse.wheel(0, 620)
            trace.append(f"滚动页面 {index + 1}/{scrolls}")
            page.wait_for_timeout(250)
        except Exception:  # pragma: no cover - browser failures are provider-specific.
            break
    return trace


def _click_link_to(page, target_url: str) -> bool:
    """Click the first anchor whose resolved href matches the target URL."""
    anchors = page.locator("a")
    try:
        count = min(anchors.count(), 80)
    except Exception:  # pragma: no cover - browser failures are provider-specific.
        return False
    for index in range(count):
        anchor = anchors.nth(index)
        try:
            href = anchor.get_attribute("href", timeout=600)
        except Exception:  # pragma: no cover - browser failures are provider-specific.
            continue
        resolved = urljoin(page.url, href or "").rstrip("/")
        if not _same_detail_target(resolved, target_url):
            continue
        try:
            anchor.scroll_into_view_if_needed(timeout=2_000)
            time.sleep(0.2)
            anchor.click(timeout=4_000)
            return True
        except Exception:  # pragma: no cover - browser failures are provider-specific.
            return False
    return False


def _same_detail_target(candidate_url: str, target_url: str) -> bool:
    """Match a detail link by origin and path, ignoring tracking query parameters."""
    try:
        candidate = urlparse(candidate_url)
        target = urlparse(target_url)
    except ValueError:
        return candidate_url.rstrip("/") == target_url.rstrip("/")
    candidate_host = (candidate.hostname or "").lower()
    target_host = (target.hostname or "").lower()
    if candidate_host and target_host and candidate_host != target_host:
        return False
    candidate_path = candidate.path.rstrip("/")
    target_path = target.path.rstrip("/")
    return bool(candidate_path and candidate_path == target_path)

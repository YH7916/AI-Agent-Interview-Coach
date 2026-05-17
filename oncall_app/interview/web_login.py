"""Browser-login metadata and login-wall detection."""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

STRONG_LOGIN_MARKERS = ("sign in", "log in", "请先登录", "扫码登录", "验证码")
WEAK_LOGIN_MARKERS = ("登录", "登陆")
CONTENT_MARKERS = ("面经", "面试", "问题", "回答", "agent", "rag", "llm", "项目", "实习")
LOGGED_IN_MARKERS = ("退出登录", "个人中心", "我的主页", "账号设置", "消息")


@dataclass(frozen=True)
class LoginProbeResult:
    """Read-only login-state probe result."""

    state: str
    confidence: str
    indicators: list[str]
    reason: str
    needs_login: bool


def normalize_host(raw: str) -> str:
    """Normalize a host or URL for metadata lookup."""
    text = raw.strip()
    if "://" not in text:
        text = "https://" + text
    host = urlparse(text).netloc.split("@")[-1].split(":")[0].lower()
    if host in {"www.nowcoder.com", "www.xiaohongshu.com", "www.zhihu.com"}:
        return host.removeprefix("www.")
    return host


def profile_name_for_host(host: str) -> str:
    """Return a filesystem-safe browser profile name."""
    safe = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")
    return f"web-fetch-{safe}"


def detect_login_wall(html: str, final_url: str) -> LoginProbeResult:
    """Detect whether fetched HTML looks like a login wall."""
    folded = html.casefold()
    logged_in = [marker for marker in LOGGED_IN_MARKERS if marker.casefold() in folded]
    if logged_in:
        return LoginProbeResult("verified", "medium", logged_in, "logged-in markers found", False)
    strong_login = [marker for marker in STRONG_LOGIN_MARKERS if marker.casefold() in folded]
    if strong_login:
        return LoginProbeResult("rejected", "high", strong_login, "login-wall markers found", True)
    weak_login = [marker for marker in WEAK_LOGIN_MARKERS if marker.casefold() in folded]
    if weak_login and not _looks_like_content_page(folded):
        return LoginProbeResult("rejected", "medium", weak_login, "login-wall markers found", True)
    if "login" in final_url.casefold():
        return LoginProbeResult("rejected", "medium", ["login-url"], "final URL looks like login page", True)
    return LoginProbeResult("uncertain", "low", [], "no decisive login markers", False)


def _looks_like_content_page(folded_text: str) -> bool:
    if len(folded_text.strip()) >= 300:
        return True
    return any(marker.casefold() in folded_text for marker in CONTENT_MARKERS)

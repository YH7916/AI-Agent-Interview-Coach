"""Deterministic login-state probe for authorized source platforms."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

LoginProbeState = Literal["verified", "rejected", "uncertain"]
LoginProbeConfidence = Literal["high", "medium", "low"]
LoginProbeJudge = Callable[[str, str, tuple[str, ...]], "LoginProbeResult"]

LOGIN_WALL_MARKERS = (
    "登录",
    "登陆",
    "sign in",
    "log in",
    "请先登录",
    "扫码登录",
    "验证码",
)
HIGH_CONFIDENCE_LOGGED_IN_MARKERS = (
    ("logout", "退出登录"),
    ("account-settings", "账号设置"),
    ("profile-center", "个人中心"),
    ("user-home", "我的主页"),
    ("avatar", "avatar"),
)
MEDIUM_CONFIDENCE_LOGGED_IN_MARKERS = (
    ("message-entry", "消息"),
    ("notification-entry", "通知"),
    ("user-menu", "user-menu"),
)


@dataclass(frozen=True)
class LoginProbeResult:
    """Result of probing one browser-profile login state."""

    state: LoginProbeState
    confidence: LoginProbeConfidence
    indicators: tuple[str, ...]
    reason: str
    needs_login: bool
    llm_used: bool = False


def probe_login_state(
    html: str,
    final_url: str,
    llm_judge: LoginProbeJudge | None = None,
) -> LoginProbeResult:
    """Classify fetched page HTML as verified, rejected, or uncertain."""
    folded = html.casefold()
    login_hits = tuple(marker for marker in LOGIN_WALL_MARKERS if marker.casefold() in folded)
    if login_hits:
        return LoginProbeResult(
            state="rejected",
            confidence="high",
            indicators=login_hits,
            reason="检测到登录墙",
            needs_login=True,
        )
    if "login" in final_url.casefold():
        return LoginProbeResult(
            state="rejected",
            confidence="medium",
            indicators=("login-url",),
            reason="最终地址疑似登录页",
            needs_login=True,
        )

    high_hits = _marker_hits(folded, HIGH_CONFIDENCE_LOGGED_IN_MARKERS)
    if high_hits:
        return LoginProbeResult(
            state="verified",
            confidence="high",
            indicators=high_hits,
            reason="检测到登录后页面特征",
            needs_login=False,
        )

    medium_hits = _marker_hits(folded, MEDIUM_CONFIDENCE_LOGGED_IN_MARKERS)
    if medium_hits and llm_judge is not None:
        return llm_judge(html, final_url, medium_hits)
    if medium_hits:
        return LoginProbeResult(
            state="uncertain",
            confidence="medium",
            indicators=medium_hits,
            reason="检测到弱登录特征",
            needs_login=False,
        )

    return LoginProbeResult(
        state="uncertain",
        confidence="low",
        indicators=(),
        reason="未检测到明确登录特征",
        needs_login=False,
    )


def _marker_hits(folded_html: str, markers: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(name for name, marker in markers if marker.casefold() in folded_html)

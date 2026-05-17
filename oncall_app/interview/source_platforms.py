"""Known interview-source platforms for authorized browser sessions."""

from dataclasses import dataclass
from urllib.parse import quote_plus

SEARCH_KEYWORDS = (
    "agent 面经",
)


@dataclass(frozen=True)
class SourcePlatform:
    """A website whose login state can be managed by the product UI."""

    id: str
    label: str
    host: str
    login_url: str
    icon_path: str
    search_urls: tuple[str, ...]


SOURCE_PLATFORMS: tuple[SourcePlatform, ...] = (
    SourcePlatform(
        id="nowcoder",
        label="牛客",
        host="nowcoder.com",
        login_url="https://www.nowcoder.com",
        icon_path="/static/assets/source-platforms/nowcoder.ico",
        search_urls=tuple(
            f"https://www.nowcoder.com/search?query={quote_plus(keyword)}&type=post"
            for keyword in SEARCH_KEYWORDS
        ),
    ),
    SourcePlatform(
        id="xiaohongshu",
        label="小红书",
        host="xiaohongshu.com",
        login_url="https://www.xiaohongshu.com",
        icon_path="/static/assets/source-platforms/xiaohongshu.ico",
        search_urls=tuple(
            f"https://www.xiaohongshu.com/search_result?keyword={quote_plus(keyword)}"
            for keyword in SEARCH_KEYWORDS
        ),
    ),
    SourcePlatform(
        id="zhihu",
        label="知乎",
        host="zhihu.com",
        login_url="https://www.zhihu.com",
        icon_path="/static/assets/source-platforms/zhihu.ico",
        search_urls=tuple(
            f"https://www.zhihu.com/search?type=content&q={quote_plus(keyword)}"
            for keyword in SEARCH_KEYWORDS
        ),
    ),
)


def get_source_platform(platform_id: str) -> SourcePlatform:
    """Return one known source platform by id."""
    for platform in SOURCE_PLATFORMS:
        if platform.id == platform_id:
            return platform
    raise KeyError(platform_id)

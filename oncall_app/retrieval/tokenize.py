"""Tokenization for Chinese and mixed technical SOP text."""

import re
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message="pkg_resources is deprecated as an API",
        category=UserWarning,
    )
    import jieba

jieba.setLogLevel(60)

TECH_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+_.-]*|[0-9]+|&")
CHINESE_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def _chinese_bigrams(text: str) -> list[str]:
    """Return overlapping Chinese character bigrams."""
    chars = CHINESE_CHAR_PATTERN.findall(text)
    return ["".join(chars[index : index + 2]) for index in range(max(0, len(chars) - 1))]


def tokenize(text: str) -> list[str]:
    """Tokenize Chinese SOP text with technical-token preservation."""
    tech_tokens = [match.group(0).casefold() for match in TECH_TOKEN_PATTERN.finditer(text)]
    jieba_tokens = [
        token.casefold()
        for token in jieba.cut_for_search(text)
        if token.strip() and not token.isspace()
    ]
    return [*tech_tokens, *jieba_tokens, *_chinese_bigrams(text)]

"""Evaluation metrics for retrieval and tool-calling behavior."""


def hit_rate_at_k(expected: list[list[str]], actual: list[list[str]], k: int) -> float:
    """Return the fraction of cases with any expected item in the top-k results."""
    _validate_batches(expected, actual)
    if not expected:
        return 0.0

    hits = 0
    for expected_items, actual_items in zip(expected, actual, strict=True):
        expected_set = set(expected_items)
        top_k = actual_items[:k]
        if (not expected_set and not top_k) or any(item in expected_set for item in top_k):
            hits += 1
    return hits / len(expected)


def mrr(expected: list[list[str]], actual: list[list[str]]) -> float:
    """Return mean reciprocal rank for expected identifiers."""
    _validate_batches(expected, actual)
    if not expected:
        return 0.0

    reciprocal_ranks = []
    for expected_items, actual_items in zip(expected, actual, strict=True):
        expected_set = set(expected_items)
        if not expected_set:
            reciprocal_ranks.append(1.0 if not actual_items else 0.0)
            continue
        rank = next(
            (
                index
                for index, item in enumerate(actual_items, start=1)
                if item in expected_set
            ),
            0,
        )
        reciprocal_ranks.append(1 / rank if rank else 0.0)
    return sum(reciprocal_ranks) / len(reciprocal_ranks)


def tool_file_accuracy(expected: list[list[str]], actual: list[list[str]]) -> float:
    """Return the fraction of agent cases that read every expected SOP file."""
    _validate_batches(expected, actual)
    if not expected:
        return 0.0

    correct = 0
    for expected_files, actual_files in zip(expected, actual, strict=True):
        expected_set = set(expected_files)
        actual_set = set(actual_files)
        if (not expected_set and not actual_set) or expected_set.issubset(actual_set):
            correct += 1
    return correct / len(expected)


def keyword_coverage(expected: list[list[str]], answers: list[str]) -> float:
    """Return the fraction of must-include answer keywords that appear."""
    if len(expected) != len(answers):
        raise ValueError("expected and answers must have the same length")

    total = sum(len(items) for items in expected)
    if total == 0:
        return 1.0

    found = 0
    for keywords, answer in zip(expected, answers, strict=True):
        folded_answer = answer.casefold()
        found += sum(1 for keyword in keywords if keyword.casefold() in folded_answer)
    return found / total


def memory_recall_at_1(expected: list[str], actual: list[str]) -> float:
    """Return fraction of expected memory strings found in top-1 recall text."""
    if len(expected) != len(actual):
        raise ValueError("expected and actual must have the same length")
    if not expected:
        return 0.0

    hits = 0
    for expected_text, actual_text in zip(expected, actual, strict=True):
        if expected_text.casefold() in actual_text.casefold():
            hits += 1
    return hits / len(expected)


def _validate_batches(expected: list[list[str]], actual: list[list[str]]) -> None:
    """Validate pairwise metric inputs."""
    if len(expected) != len(actual):
        raise ValueError("expected and actual must have the same length")

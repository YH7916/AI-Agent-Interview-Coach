"""Quality scoring for background source collection jobs."""

from __future__ import annotations


def build_source_quality(
    *,
    questions: int,
    unique_questions: int,
    duplicate_questions: int,
    rejected_blocks: int,
    fallback_pages: int,
) -> dict[str, object]:
    """Return product-facing quality metrics for one collection job."""
    effective_rate = round(unique_questions / questions, 2) if questions else 0.0
    duplicate_rate = round(duplicate_questions / questions, 2) if questions else 0.0
    if questions <= 0:
        status = "low"
        message = f"未抽到有效题目，过滤 {rejected_blocks} 个噪声块"
    elif unique_questions <= 0:
        status = "partial"
        message = f"本次均为重复题，重复 {duplicate_questions}"
    elif fallback_pages > 0:
        status = "partial"
        message = f"部分页面使用通用抽取，新增 {unique_questions} / 重复 {duplicate_questions}"
    else:
        status = "good"
        message = f"采集有效，新增 {unique_questions} / 重复 {duplicate_questions}"
    return {
        "quality_status": status,
        "quality_message": message,
        "effective_question_rate": effective_rate,
        "duplicate_rate": duplicate_rate,
        "rejected_blocks": rejected_blocks,
        "fallback_pages": fallback_pages,
    }

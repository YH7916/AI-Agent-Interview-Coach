"""Short-term working memory for interview-agent sessions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from oncall_app.interview.models import (
    SessionMemoryAtom,
    SessionMemoryCanvas,
    SessionMemoryRef,
    SessionMemoryTurn,
)
from oncall_app.interview.store import InterviewStore
from oncall_app.memory.models import utc_now
from oncall_app.models import ConversationTurn

RECENT_RAW_TURNS = 8
RECENT_ATOMS = 40
REF_THRESHOLD_CHARS = 1400
PROMPT_CONTEXT_MAX_CHARS = 2800

AtomKind = Literal["goal", "constraint", "state", "topic", "open_question", "decision", "feedback"]


@dataclass(frozen=True)
class ShortTermContext:
    """Prompt-ready short-term memory context."""

    session_id: str
    prompt_block: str
    canvas: SessionMemoryCanvas | None
    atoms: list[SessionMemoryAtom]
    recent_turns: list[SessionMemoryTurn]


class ShortTermMemoryService:
    """Maintain raw turns, atoms, refs, and an active symbolic canvas."""

    def __init__(self, store: InterviewStore):
        self.store = store

    def build_context(
        self,
        session_id: str,
        incoming_history: list[ConversationTurn] | None = None,
    ) -> ShortTermContext:
        """Build compact context for the next model request."""
        normalized_session_id = _session_id(session_id)
        canvas = self.store.get_session_memory_canvas(normalized_session_id)
        atoms = self.store.list_session_memory_atoms(normalized_session_id, limit=RECENT_ATOMS)
        recent_turns = self.store.list_session_memory_turns(normalized_session_id, limit=RECENT_RAW_TURNS)
        prompt_block = _prompt_block(
            normalized_session_id,
            canvas,
            atoms,
            recent_turns,
            incoming_history or [],
        )
        return ShortTermContext(
            session_id=normalized_session_id,
            prompt_block=prompt_block,
            canvas=canvas,
            atoms=atoms,
            recent_turns=recent_turns,
        )

    def record_exchange(
        self,
        session_id: str,
        user_message: str,
        assistant_answer: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> SessionMemoryCanvas:
        """Capture one completed exchange and refresh the active canvas."""
        normalized_session_id = _session_id(session_id)
        base_metadata = metadata or {}
        user_turn = self._store_turn(normalized_session_id, "user", user_message, base_metadata)
        assistant_turn = self._store_turn(
            normalized_session_id,
            "assistant",
            assistant_answer,
            {**base_metadata, "paired_user_turn_id": user_turn.id},
        )
        for atom in [
            *self._atoms_for_turn(user_turn),
            *self._atoms_for_turn(assistant_turn),
        ]:
            self.store.add_session_memory_atom(atom)
        return self.refresh_canvas(normalized_session_id)

    def refresh_canvas(self, session_id: str) -> SessionMemoryCanvas:
        """Rebuild the symbolic canvas from recent atoms and raw turns."""
        normalized_session_id = _session_id(session_id)
        atoms = self.store.list_session_memory_atoms(normalized_session_id, limit=RECENT_ATOMS)
        recent_turns = self.store.list_session_memory_turns(normalized_session_id, limit=RECENT_RAW_TURNS)
        summary = _summary_from_atoms(atoms, recent_turns)
        canvas = SessionMemoryCanvas(
            session_id=normalized_session_id,
            mermaid=_mermaid_canvas(normalized_session_id, summary, atoms),
            summary=summary,
            updated_at=utc_now(),
        )
        return self.store.upsert_session_memory_canvas(canvas)

    def _store_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, object],
    ) -> SessionMemoryTurn:
        text = str(content or "").strip()
        ref_ids: list[str] = []
        if len(text) > REF_THRESHOLD_CHARS:
            ref = self.store.add_session_memory_ref(
                SessionMemoryRef(
                    session_id=session_id,
                    kind=f"{role}_long_turn",
                    title=f"{role} turn offload",
                    content=text,
                    token_estimate=max(1, len(text) // 4),
                    metadata={"role": role, **metadata},
                )
            )
            ref_ids.append(ref.id)
        return self.store.add_session_memory_turn(
            SessionMemoryTurn(
                session_id=session_id,
                role=role,
                content=_clip(text, REF_THRESHOLD_CHARS),
                metadata={**metadata, "ref_ids": ref_ids},
            )
        )

    def _atoms_for_turn(self, turn: SessionMemoryTurn) -> list[SessionMemoryAtom]:
        text = turn.content.strip()
        if not text:
            return []
        raw_ref_ids = turn.metadata.get("ref_ids", [])
        ref_ids = [item for item in raw_ref_ids if isinstance(item, str)] if isinstance(raw_ref_ids, list) else []
        atoms: list[SessionMemoryAtom] = []
        if turn.role == "user":
            atoms.extend(_user_atoms(turn, text, ref_ids))
        else:
            atoms.extend(_assistant_atoms(turn, text, ref_ids))
        if not atoms:
            atoms.append(_atom(turn, "state", f"{turn.role}: {_clip(text, 96)}", ref_ids))
        return atoms


def _user_atoms(turn: SessionMemoryTurn, text: str, ref_ids: list[str]) -> list[SessionMemoryAtom]:
    atoms: list[SessionMemoryAtom] = []
    if re.search(r"(我想|我要|希望|目标|做成|落地|上线|真实产品)", text):
        atoms.append(_atom(turn, "goal", _clip(text, 140), ref_ids))
    if re.search(r"(不要|不能|不应该|必须|一定|只|别|希望.*不要|保持|遵循)", text):
        atoms.append(_atom(turn, "constraint", _clip(text, 140), ref_ids))
    if re.search(r"(为什么|怎么|什么意思|是否|吗|？|\?)", text):
        atoms.append(_atom(turn, "open_question", _clip(text, 140), ref_ids))
    topic = _topic_from_text(text)
    if topic:
        atoms.append(_atom(turn, "topic", topic, ref_ids))
    mode = _mode_from_text(text)
    if mode:
        atoms.append(_atom(turn, "state", mode, ref_ids))
    if re.search(r"(不对|失败|报错|太差|不完善|半吊子|没用|422|Request failed)", text, flags=re.I):
        atoms.append(_atom(turn, "feedback", _clip(text, 140), ref_ids))
    return atoms


def _assistant_atoms(turn: SessionMemoryTurn, text: str, ref_ids: list[str]) -> list[SessionMemoryAtom]:
    atoms: list[SessionMemoryAtom] = []
    if re.search(r"(我会|已经|接下来|下一步|建议|应该|需要)", text):
        atoms.append(_atom(turn, "decision", _clip(text, 140), ref_ids))
    topic = _topic_from_text(text)
    if topic:
        atoms.append(_atom(turn, "topic", topic, ref_ids))
    return atoms


def _atom(
    turn: SessionMemoryTurn,
    kind: AtomKind,
    content: str,
    ref_ids: list[str],
) -> SessionMemoryAtom:
    return SessionMemoryAtom(
        session_id=turn.session_id,
        turn_id=turn.id,
        kind=kind,
        content=content,
        ref_ids=ref_ids,
        metadata={"role": turn.role},
    )


def _summary_from_atoms(
    atoms: list[SessionMemoryAtom],
    recent_turns: list[SessionMemoryTurn],
) -> dict[str, object]:
    by_kind = {
        kind: _unique_recent([atom.content for atom in atoms if atom.kind == kind], limit=5)
        for kind in ("goal", "constraint", "state", "topic", "open_question", "decision", "feedback")
    }
    last_user = next((turn.content for turn in reversed(recent_turns) if turn.role == "user"), "")
    current_topic = by_kind["topic"][-1] if by_kind["topic"] else _topic_from_text(last_user) or "interview_coach"
    mode = by_kind["state"][-1] if by_kind["state"] else _mode_from_text(last_user) or "free_dialog"
    next_step = _next_step(by_kind, current_topic)
    return {
        "mode": mode,
        "current_topic": current_topic,
        "goals": by_kind["goal"],
        "constraints": by_kind["constraint"],
        "open_questions": by_kind["open_question"],
        "decisions": by_kind["decision"],
        "feedback": by_kind["feedback"],
        "last_user_intent": _clip(last_user, 180),
        "next_step": next_step,
    }


def _prompt_block(
    session_id: str,
    canvas: SessionMemoryCanvas | None,
    atoms: list[SessionMemoryAtom],
    recent_turns: list[SessionMemoryTurn],
    incoming_history: list[ConversationTurn],
) -> str:
    lines = [
        "Short-term working memory for this session.",
        "Use it as compact, recoverable context. Do not expose internal ids unless asked.",
        f"session_id: {session_id}",
    ]
    if canvas is not None:
        lines.extend(
            [
                "Active canvas:",
                "```mermaid",
                canvas.mermaid,
                "```",
                "State summary:",
                _summary_lines(canvas.summary),
            ]
        )
    else:
        lines.append("Active canvas: not built yet.")
    if atoms:
        lines.append("Recent atoms:")
        for atom in atoms[-10:]:
            ref_note = f" refs={','.join(atom.ref_ids)}" if atom.ref_ids else ""
            lines.append(f"- {atom.id} [{atom.kind}] {_clip(atom.content, 120)}{ref_note}")
    raw_turns = recent_turns or _incoming_history_turns(incoming_history)
    if raw_turns:
        lines.append("Recent raw turns:")
        for turn in raw_turns[-6:]:
            lines.append(f"- {turn.role}: {_clip(turn.content, 180)}")
    return _clip("\n".join(lines), PROMPT_CONTEXT_MAX_CHARS)


def _summary_lines(summary: dict[str, object]) -> str:
    lines = [
        f"- mode: {summary.get('mode') or 'free_dialog'}",
        f"- current_topic: {summary.get('current_topic') or 'interview_coach'}",
        f"- last_user_intent: {summary.get('last_user_intent') or ''}",
        f"- next_step: {summary.get('next_step') or ''}",
    ]
    for key in ("goals", "constraints", "open_questions", "feedback"):
        values = summary.get(key)
        if isinstance(values, list) and values:
            lines.append(f"- {key}: " + " | ".join(str(item) for item in values[-3:]))
    return "\n".join(lines)


def _mermaid_canvas(
    session_id: str,
    summary: dict[str, object],
    atoms: list[SessionMemoryAtom],
) -> str:
    lines = [
        "graph TD",
        f'  S["session:{_mermaid_label(session_id, 32)}"]',
        f'  M["mode:{_mermaid_label(str(summary.get("mode") or "free_dialog"), 48)}"]',
        f'  T["topic:{_mermaid_label(str(summary.get("current_topic") or "interview_coach"), 48)}"]',
        f'  N["next:{_mermaid_label(str(summary.get("next_step") or ""), 64)}"]',
        "  S --> M",
        "  S --> T",
        "  T --> N",
    ]
    for atom in atoms[-8:]:
        node_id = re.sub(r"[^A-Za-z0-9_]", "_", atom.id)
        lines.append(f'  {node_id}["{atom.kind}:{_mermaid_label(atom.content, 52)}"]')
        lines.append(f"  T --> {node_id}")
    return "\n".join(lines)


def _incoming_history_turns(history: list[ConversationTurn]) -> list[SessionMemoryTurn]:
    return [
        SessionMemoryTurn(
            session_id="incoming",
            role=turn.role,
            content=turn.content,
            metadata={"source": "incoming_history"},
        )
        for turn in history[-RECENT_RAW_TURNS:]
        if turn.content.strip()
    ]


def _next_step(by_kind: dict[str, list[str]], current_topic: str) -> str:
    if by_kind["open_question"]:
        return f"answer_or_clarify: {_clip(by_kind['open_question'][-1], 80)}"
    if by_kind["feedback"]:
        return "acknowledge feedback and adjust the agent behavior"
    if current_topic and current_topic != "interview_coach":
        return f"continue around {current_topic} with concrete tradeoffs and eval"
    return "continue free-form interview coaching"


def _topic_from_text(text: str) -> str:
    folded = text.casefold()
    if re.search(r"(短期记忆|长期记忆|memory|l0|l1|l2|l3|compact|上下文)", folded):
        return "memory"
    if re.search(r"(rag|召回|检索|rerank|向量|chunk)", folded):
        return "rag"
    if re.search(r"(eval|评测|grader|指标|回归)", folded):
        return "agent_eval"
    if re.search(r"(采集|登录态|牛客|小红书|知乎|浏览器|playwright)", folded):
        return "source_collection"
    if re.search(r"(面试|追问|简历|回答|面经)", folded):
        return "mock_interview"
    if re.search(r"(agent|react|tool|工具调用)", folded):
        return "agent_architecture"
    return ""


def _mode_from_text(text: str) -> str:
    if re.search(r"(开始面试|模拟面试|考我|来一场)", text):
        return "mock_interview"
    if re.search(r"(采集|搜集|抓取|入库).*(面经|题)", text):
        return "source_collection"
    if re.search(r"(讲|解释|解析).*(题|rag|memory|agent)", text, flags=re.I):
        return "explain_question"
    return ""


def _unique_recent(values: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in reversed(values):
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return list(reversed(result))


def _session_id(value: str) -> str:
    text = str(value or "default").strip()
    return text[:120] or "default"


def _clip(text: str, limit: int) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return f"{value[: max(0, limit - 1)].rstrip()}…"


def _mermaid_label(text: str, limit: int) -> str:
    return _clip(text, limit).replace('"', "'").replace("[", "(").replace("]", ")")

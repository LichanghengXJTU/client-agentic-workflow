from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st


def section_header(title: str, subtitle: str | None = None) -> None:
    st.subheader(title)
    if subtitle:
        st.caption(subtitle)


def git_write_guard(
    key_prefix: str,
    command_preview: str,
    phrase_required: str | None = None,
) -> bool:
    st.code(command_preview, language="bash")
    ok = st.checkbox("我已确认上述命令将修改 git 历史 / I confirm the git operation", key=f"{key_prefix}_check")
    if phrase_required:
        phrase = st.text_input(
            f"输入确认短语 / Enter phrase: {phrase_required}",
            key=f"{key_prefix}_phrase",
        )
        return ok and phrase == phrase_required
    return ok


def status_badge(label: str, value: str) -> None:
    st.markdown(f"**{label}:** `{value}`")


def subtask_card(subtask: dict[str, Any], selected: bool = False) -> None:
    prefix = "### " if selected else "#### "
    st.markdown(f"{prefix}{subtask.get('id', '-')} | {subtask.get('title', '(untitled)')}")
    c1, c2, c3 = st.columns(3)
    with c1:
        status_badge("Owner", str(subtask.get("owner", "-")))
    with c2:
        status_badge("Priority", str(subtask.get("priority", "-")))
    with c3:
        status_badge("Status", str(subtask.get("status", "-")))
    objective = str(subtask.get("objective", "")).strip()
    if objective:
        st.caption(objective)


def activity_event_card(event: dict[str, Any]) -> None:
    title = str(event.get("title", "(untitled)"))
    event_type = str(event.get("type", "event"))
    when = str(event.get("time", ""))
    st.markdown(f"**[{event_type}] {title}**")
    if when:
        st.caption(when)
    summary = str(event.get("summary", "")).strip()
    if summary:
        st.write(summary)
    path = str(event.get("path", "")).strip()
    if path:
        st.code(path, language="text")
    meta = []
    if event.get("model"):
        meta.append(f"model={event['model']}")
    if event.get("route"):
        meta.append(f"route={event['route']}")
    if event.get("status"):
        meta.append(f"status={event['status']}")
    if meta:
        st.caption(" | ".join(meta))
    st.markdown("---")


def image_gallery(paths: list[str]) -> None:
    if not paths:
        st.info("No image artifacts found.")
        return
    for path in paths:
        p = Path(path)
        if not p.exists():
            continue
        st.image(str(p), caption=str(p), use_container_width=True)


def iso_or_dash(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.isoformat(timespec="seconds")
    except Exception:
        return text

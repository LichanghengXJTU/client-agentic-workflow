from __future__ import annotations

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

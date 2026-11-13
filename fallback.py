"""Standard (no-AI) explanations. These guarantee the Magic Layer is still useful when AI is off,
over quota, or its answer failed a check. Strings come from shared/strings.json (English + Hindi)
so the website's offline mode shows identical wording.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_STRINGS: dict | None = None
HEADER_RE = re.compile(r"^[\u2713\u2714\u2611\s]*(calculation (result|successful)|result|answer|magnification)\b", re.I)


def strings() -> dict:
    global _STRINGS
    if _STRINGS is None:
        p = Path(__file__).resolve().parent / "data" / "strings.json"
        _STRINGS = json.loads(p.read_text(encoding="utf-8"))
    return _STRINGS


def tr(lang: str, key: str, **kw) -> str:
    s = strings().get(lang) or strings()["en"]
    text = s.get(key) or strings()["en"].get(key, key)
    return text.format(**kw) if kw else text


def parse_result(text: str) -> dict:
    """Split the calculator's own result text into headline, formula line and working lines."""
    lines = [ln.strip() for ln in (text or "").replace("\r", "").split("\n") if ln.strip()]
    lines = [ln for ln in lines if not HEADER_RE.match(ln) or any(c.isdigit() for c in ln)]
    headline = next((ln for ln in lines if any(c.isdigit() for c in ln) and not ln.lower().startswith("formula")), "")
    formula = ""
    for ln in lines:
        if ln.lower().startswith("formula"):
            formula = ln.split(":", 1)[-1].strip()
            break
    if not formula:
        formula = next((ln for ln in lines if "=" in ln and re.search(r"[A-Za-z\u03b1-\u03c9]", ln)), "")
    working = [ln for ln in lines if ln != headline and not ln.lower().startswith("formula")]
    return {"headline": headline, "formula": formula, "working": working}


def pairs_text(inputs: list[dict]) -> str:
    return "; ".join(f"{i['label']} = {i['value']}" for i in inputs) or "—"


def explain(lang: str, tool_name: str, mode_label: str, registry_formula: str, inputs: list[dict], result_text: str) -> str:
    p = parse_result(result_text)
    formula = p["formula"] or registry_formula
    parts = [tr(lang, "t.about", tool=tool_name, mode=mode_label or tool_name)]
    if formula:
        parts.append(tr(lang, "t.formula", formula=formula))
    parts.append(tr(lang, "t.entered", pairs=pairs_text(inputs)))
    if p["headline"]:
        parts.append(tr(lang, "t.result", result=p["headline"]))
    parts.append(tr(lang, "t.tip"))
    return "\n".join(parts)


def steps(lang: str, result_text: str) -> str:
    p = parse_result(result_text)
    work = p["working"][:8]
    if not work and p["formula"]:
        work = [p["formula"]]
    if not work:
        return tr(lang, "t.steps_none")
    body = "\n".join(f"{i}. {w}" for i, w in enumerate(work, 1))
    return tr(lang, "t.steps_intro") + "\n" + body


def notice(lang: str, reason: str | None) -> str:
    return tr(lang, "n." + reason) if reason else ""

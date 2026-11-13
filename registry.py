"""Tool registry: the list of calculators, their modes and input fields.

The registry is generated from the real calculator pages (see tools/build_registry.js).
It is also the *safety gate*: whatever the AI (or the rules) proposes is checked here, so a wrong
or malicious answer can never name a calculator, mode or input that does not exist.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from urllib.parse import urlencode

TEXT_VALUE_RE = re.compile(r"^[A-Za-z0-9().\[\]\u00b7 \-]{1,40}$")   # chemical formulas such as Ca(OH)2
MAX_ABS_VALUE = 1e30


def _has_real_default(f: dict) -> bool:
    """Page values such as NaCl / 500 are only examples. Only constants like gravity are true defaults."""
    return f.get("default") not in (None, "") and "gravity" in f.get("label", "").lower()


class RouteError(ValueError):
    """Raised when a proposed route is not valid for the registry."""


@dataclass
class Route:
    tool_id: str
    tool_name: str
    url: str
    mode: str
    mode_label: str
    inputs: dict[str, object] = field(default_factory=dict)
    selects: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)        # ids of fields still empty
    params: dict[str, str] = field(default_factory=dict)    # exactly what the calculator URL needs
    query: str = ""

    def as_dict(self) -> dict:
        return {
            "tool_id": self.tool_id, "tool_name": self.tool_name, "url": self.url,
            "mode": self.mode, "mode_label": self.mode_label,
            "inputs": self.inputs, "selects": self.selects, "missing": self.missing,
            "complete": not self.missing, "params": self.params, "query": self.query,
        }


class Registry:
    def __init__(self, data: dict):
        self.tools: dict[str, dict] = {t["id"]: t for t in data["tools"]}
        self.chapters: list[dict] = data.get("chapters", [])
        self.version = data.get("version", 1)

    @classmethod
    def load(cls, path: str) -> "Registry":
        with open(path, "r", encoding="utf-8") as fh:
            return cls(json.load(fh))

    # ---- lookups -------------------------------------------------------------------------
    def tool(self, tool_id: str) -> dict:
        t = self.tools.get(tool_id)
        if not t:
            raise RouteError("unknown tool")
        return t

    def mode_key(self, tool: dict, mode: str | None) -> str:
        modes = tool["modes"]
        if not tool.get("modeSelect"):
            return ""
        m = "" if mode is None else str(mode)
        if m not in modes:
            raise RouteError("unknown mode")
        return m

    def fields(self, tool: dict, mode: str) -> list[dict]:
        return tool["modes"][mode]["fields"]

    def numeric_fields(self, tool: dict, mode: str) -> list[dict]:
        return [f for f in self.fields(tool, mode) if f.get("type") != "text"]

    def formula_for(self, tool: dict) -> str:
        return tool.get("formula", "")

    def chapter_for(self, tool: dict) -> dict | None:
        url = tool.get("chapter")
        return next((c for c in self.chapters if c["url"] == url), None) if url else None

    def related_tools(self, tool: dict) -> list[dict]:
        by_url = {t["url"]: t for t in self.tools.values()}
        return [by_url[u] for u in tool.get("related", []) if u in by_url]

    # ---- validation (the safety gate) --------------------------------------------------------
    def validate_route(self, tool_id: str, mode: str | None, inputs: dict | None, selects: dict | None = None) -> Route:
        tool = self.tool(str(tool_id))
        mk = self.mode_key(tool, mode)
        allowed = {f["id"]: f for f in self.fields(tool, mk)}
        clean_inputs: dict[str, object] = {}
        provided = inputs or {}
        for key in [k for k in allowed if k in provided]:   # field order, so the URL is always the same
            raw = provided[key]
            f = allowed[key]
            if f.get("type") == "text":
                s = str(raw).strip()
                if not TEXT_VALUE_RE.match(s):
                    raise RouteError("invalid text value for " + key)
                clean_inputs[key] = s
            else:
                if isinstance(raw, bool):
                    raise RouteError("invalid number for " + key)
                try:
                    v = float(raw)
                except (TypeError, ValueError):
                    raise RouteError("invalid number for " + key)
                if not math.isfinite(v) or abs(v) > MAX_ABS_VALUE:
                    raise RouteError("number out of range for " + key)
                clean_inputs[key] = int(v) if v == int(v) and abs(v) < 1e15 else v
        clean_selects: dict[str, str] = {}
        for ex in tool.get("extras", []):
            if selects and ex["id"] in selects:
                val = str(selects[ex["id"]])
                if val not in {o["v"] for o in ex["options"]}:
                    raise RouteError("invalid option for " + ex["id"])
                clean_selects[ex["id"]] = val
        params: dict[str, str] = {}
        if tool.get("modeSelect"):
            params[tool["modeSelect"]] = mk
        params.update(clean_selects)
        params.update({k: str(v) for k, v in clean_inputs.items()})
        return Route(
            tool_id=tool["id"], tool_name=tool["name"], url=tool["url"], mode=mk,
            mode_label=tool["modes"][mk]["label"], inputs=clean_inputs, selects=clean_selects,
            missing=[k for k, f in allowed.items() if k not in clean_inputs and not _has_real_default(f)], params=params,
            query=urlencode(params),
        )

    # ---- compact description for AI prompts ------------------------------------------------------
    def describe_for_prompt(self, tool_ids: list[str]) -> str:
        lines = []
        for tid in tool_ids:
            t = self.tools[tid]
            lines.append(f"TOOL {t['id']} ({t['name']}); mode select id: {t.get('modeSelect') or 'none'}")
            for mk, m in t["modes"].items():
                fs = ", ".join(f"{f['id']}={f['label']}" for f in m["fields"])
                lines.append(f'  mode "{mk}" = {m["label"] or t["name"]}: {fs}')
            for ex in t.get("extras", []):
                lines.append(f"  extra select {ex['id']}: " + "/".join(o["v"] for o in ex["options"]))
        return "\n".join(lines)

"""Deterministic routing and formula finding. Works with no AI, no network, no cost.

AI is only consulted when these rules are not confident enough (see service.py).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from . import text as T
from .registry import Registry, Route, RouteError

ELEMENTS = (
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr "
    "Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir "
    "Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr"
).split()
_EL_ALT = "|".join(sorted(ELEMENTS, key=lambda e: -len(e)))
_FORMULA_RE = re.compile(r"(?<![A-Za-z0-9])((?:(?:" + _EL_ALT + r")\d*|\((?:(?:" + _EL_ALT + r")\d*)+\)\d*)+)(?![A-Za-z0-9])")
_ELEMENT_TOKEN = re.compile(_EL_ALT)

UNIT_CANON = {
    "sec": "s", "second": "s", "seconds": "s", "mins": "min", "minute": "min", "minutes": "min",
    "hr": "h", "hrs": "h", "hour": "h", "hours": "h", "newton": "n", "newtons": "n", "joule": "j", "joules": "j",
    "watt": "w", "watts": "w", "volt": "v", "volts": "v", "amp": "a", "amps": "a", "ampere": "a", "amperes": "a",
    "ohm": "ω", "ohms": "ω", "litre": "l", "litres": "l", "liter": "l", "liters": "l", "kmph": "km/h", "km/hr": "km/h",
    "degree": "°", "degrees": "°", "deg": "°",
}
CONVERSIONS = {
    ("g", "kg"): 0.001, ("mg", "kg"): 1e-6, ("kg", "g"): 1000.0, ("km/h", "m/s"): 1 / 3.6, ("m/s", "km/h"): 3.6,
    ("km", "m"): 1000.0, ("cm", "m"): 0.01, ("mm", "m"): 0.001, ("m", "cm"): 100.0, ("m", "km"): 0.001,
    ("min", "s"): 60.0, ("h", "s"): 3600.0, ("s", "min"): 1 / 60, ("s", "h"): 1 / 3600, ("min", "h"): 1 / 60,
    ("h", "min"): 60.0, ("kj", "j"): 1000.0, ("kw", "w"): 1000.0, ("kpa", "pa"): 1000.0, ("ml", "l"): 0.001,
    ("l", "ml"): 1000.0,
}
FILLER = {"is", "of", "the", "a", "an", "was", "are", "at", "with", "and", "has", "have", "when", "if", "given", "equal", "equals", "to", "as", "by", "for", "on", "in", "moving"}
LABEL_STOP = {"the", "of", "and", "for", "per", "unit", "value", "known", "solution", "chemical", "in"}


def canon_unit(u: str | None) -> str | None:
    if not u:
        return None
    u = u.lower().replace("²", "2").replace("³", "3")
    return UNIT_CANON.get(u, u)


def label_unit(label: str) -> str | None:
    m = re.search(r"\(([^)]*)\)", T.normalise(label))
    return canon_unit(m.group(1).strip()) if m else None


def extract_formula(question: str) -> str | None:
    """Find a chemical formula such as NaCl, H2O, Ca(OH)2 in the ORIGINAL (case-sensitive) text."""
    for m in _FORMULA_RE.finditer(question or ""):
        cand = m.group(1)
        n_elements = len(_ELEMENT_TOKEN.findall(re.sub(r"\d", "", cand)))
        if n_elements >= 2 or re.search(r"\d", cand):
            if cand.lower() in ("a", "i"):
                continue
            return cand
    return None


@dataclass
class Quantity:
    value: float
    unit: str | None
    cls: str | None
    before: str          # the words just before the number, e.g. "initial velocity" or "r ="


def extract_quantities(question: str) -> list[Quantity]:
    t = T.normalise(question)
    out: list[Quantity] = []
    prev_end = 0
    for m in T.QUANTITY_RE.finditer(t):
        raw = m.group(1)
        try:
            v = float(raw)
        except ValueError:
            continue
        unit = canon_unit(m.group(2))
        raw_before = t[max(prev_end, m.start() - 28): m.start()]
        prev_end = m.end()
        words = [w for w in re.findall(r"[a-z]+", raw_before) if w not in FILLER]
        # keep the raw text only when it ends in a symbol such as "r =", plus the last two real words
        sym_tail = re.search(r"(?<![a-z])[a-z]\s*=?\s*$", raw_before)
        before = " ".join(words[-2:]) + ((" " + sym_tail.group(0)) if sym_tail else "")
        out.append(Quantity(v, unit, T.unit_class(unit), before))
    return out


# Unit classes where "5 g" vs "5 kg" really matters; for these we never guess the unit.
AMBIGUOUS_CLASSES = {"length", "time", "volume", "mass", "velocity", "pressure", "energy", "power", "temperature"}
KEY_WORDS = set(T.LABEL_WORD_CLASS) | {
    "initial", "final", "moles", "mole", "molarity", "concentration", "formula", "heat", "specific", "capacity",
    "coefficient", "friction", "normal", "diameter", "spring", "constant", "extension", "amplitude", "torque",
    "inertia", "momentum", "impulse", "focal", "object", "image", "magnification", "gravity", "weight",
}


def _stem(w: str) -> str:
    for suf in ("ing", "es", "ed", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def _label_words(label: str) -> list[str]:
    base = re.sub(r"\([^)]*\)", " ", T.normalise(label))
    return [w for w in re.findall(r"[a-z]{3,}", base) if w in KEY_WORDS and w not in LABEL_STOP]


def _symbols(label: str) -> set[str]:
    syms = {w.lower() for w in re.findall(r"(?<![A-Za-z])[A-Za-z](?![A-Za-z])", re.sub(r"\([^)]*\)", " ", label))}
    if "gravity" in label.lower():
        syms.add("g")
    return syms


def _pair_score(q: Quantity, f: dict) -> float:
    s = 0.0
    is_constant = "gravity" in f["label"].lower()     # g has a sensible default; never grab "2 m/s2" for it by unit alone
    fc = T.label_class(f["label"])
    if q.cls and fc and q.cls == fc and not is_constant:
        s += 3
    clash = bool(q.cls and fc and q.cls != fc)     # e.g. an acceleration can never be a mass
    before = q.before
    words = _label_words(f["label"])
    bw = {_stem(x) for x in re.findall(r"[a-z]+", before)}
    if any(_stem(w) in bw for w in words):
        s += 4
    for sym in _symbols(f["label"]):
        if re.search(r"(?<![a-z])" + re.escape(sym) + r"\s*=?\s*$", before):
            s += 5
    if clash and not is_constant:
        s -= 5
    return max(0.0, s)


def _converted(q: Quantity, f: dict) -> float | None:
    """Value in the unit the calculator field expects, or None if we cannot convert safely."""
    target = label_unit(f["label"])
    if not target or not q.unit or target == q.unit:
        return q.value
    factor = CONVERSIONS.get((q.unit, target))
    if factor is None:
        return None
    return float(f"{q.value * factor:.12g}")


def assign_quantities(question: str, tool: dict, fields: list[dict]) -> tuple[dict[str, float], dict[str, str]]:
    """Match numbers in the question to calculator fields. Ambiguous matches are left empty on purpose."""
    quantities = extract_quantities(question)
    inputs: dict[str, float] = {}
    selects: dict[str, str] = {}
    free_q = list(range(len(quantities)))
    free_f = [f for f in fields if f.get("type") != "text"]
    scores = {(i, f["id"]): _pair_score(quantities[i], f) for i in free_q for f in free_f}
    while True:
        best = max(((s, i, fid) for (i, fid), s in scores.items() if i in free_q and fid in {f["id"] for f in free_f}), default=None)
        if not best or best[0] < 3:
            break
        s, i, fid = best
        rivals = [x for (j, g), x in scores.items() if ((j == i and g != fid) or (g == fid and j != i)) and j in free_q and g in {f["id"] for f in free_f} and x >= s]
        free_q.remove(i)
        free_f = [f for f in free_f if f["id"] != fid]
        if rivals:
            continue                                  # tie: ambiguous, skip this pair
        f = next(f for f in fields if f["id"] == fid)
        q = quantities[i]
        if label_unit(f["label"]) is None and q.unit is not None and q.cls in AMBIGUOUS_CLASSES:
            # The field has no unit in its label, so the calculator keeps the unit in a separate selector.
            chosen = None
            for ex in tool.get("extras", []):
                for o in ex["options"]:
                    if canon_unit(o["v"]) == q.unit:
                        chosen = (ex["id"], o["v"])
            if chosen is None:
                continue                              # cannot be sure of the unit: leave empty rather than guess
            selects[chosen[0]] = chosen[1]
            inputs[fid] = q.value
            continue
        val = _converted(q, f)
        if val is not None:
            inputs[fid] = val
    return inputs, selects


# -------------------------------------------------------------------------------------------------
@dataclass
class RuleResult:
    route: Route | None
    confidence: float
    shortlist: list[tuple[str, float]] = field(default_factory=list)
    reason: str = ""


class RuleEngine:
    def __init__(self, registry: Registry):
        self.reg = registry
        self.docs: dict[str, set[str]] = {}
        self.name_tokens: dict[str, set[str]] = {}
        df: dict[str, int] = {}
        for tid, t in registry.tools.items():
            mode_text = " ".join(m["label"] for m in t["modes"].values())
            toks = set(T.tokens(" ".join([t["name"], t.get("keywords", ""), mode_text, t["category"]])))
            self.docs[tid] = toks
            self.name_tokens[tid] = set(T.tokens(t["name"]))
            for w in toks:
                df[w] = df.get(w, 0) + 1
        n = max(1, len(registry.tools))
        self.idf = {w: math.log(1 + n / c) for w, c in df.items()}

    # ---- which calculators might this be? -----------------------------------------------------
    def shortlist(self, question: str, n: int = 5) -> list[tuple[str, float]]:
        qt = [w for w in T.tokens(question) if not re.fullmatch(r"[-+]?\d+(\.\d+)?", w)]
        sq = T.squash(question)
        scored: list[tuple[str, float]] = []
        for tid, toks in self.docs.items():
            s = 0.0
            for w in qt:
                if w in toks:
                    s += self.idf.get(w, 1.0) * (1.6 if w in self.name_tokens[tid] else 1.0)
                elif len(w) >= 4 and any(d.startswith(w[:4]) and len(d) >= 4 for d in toks):
                    s += 0.5 * self.idf.get(w, 1.0)
            for kw in self.reg.tools[tid].get("keywords", "").lower().split():
                if "=" in kw and kw in sq:
                    s += 4.0
            if s > 0:
                scored.append((tid, round(s, 3)))
        scored.sort(key=lambda x: -x[1])
        return scored[:n]

    # ---- full route: calculator + mode + inputs ----------------------------------------------------
    def route(self, question: str) -> RuleResult:
        sl = self.shortlist(question, 4)
        if not sl:
            return RuleResult(None, 0.0, [], "no_match")
        top = sl[0][1]
        target = self._target_words(question)
        best: tuple[float, Route] | None = None
        for tid, ts in sl:
            tool = self.reg.tools[tid]
            if tid == "centre-of-mass-calculator":
                continue                                           # identical field labels: needs AI or the user
            for mk in tool["modes"]:
                fields = self.reg.fields(tool, mk)
                inputs, selects = assign_quantities(question, tool, fields)
                formula = extract_formula(question) if any(f.get("type") == "text" for f in fields) else None
                if formula:
                    for f in fields:
                        if f.get("type") == "text":
                            inputs[f["id"]] = formula
                try:
                    r = self.reg.validate_route(tid, mk, inputs, selects)
                except RouteError:
                    continue
                nf = max(1, len(fields))
                coverage = len(r.inputs) / nf
                bonus = 0.0
                label_toks = set(T.tokens(r.mode_label))
                if target and target & label_toks:
                    bonus += 2.0
                score = ts / max(top, 1e-9) + 2.0 * coverage + bonus
                if not r.inputs:
                    score -= 1.0
                if best is None or score > best[0]:
                    best = (score, r)
        if not best:
            return RuleResult(None, 0.1, sl, "no_route")
        r = best[1]
        second = sl[1][1] if len(sl) > 1 else 0.0
        tool_clear = top >= 2.0 and (second == 0 or top >= 1.25 * second)
        picked_score = dict(sl).get(r.tool_id, 0.0)
        if r.tool_id != sl[0][0]:
            tool_clear = tool_clear and picked_score >= 0.8 * top
        n_numbers = len(extract_quantities(question))
        n_assigned = len([k for k in r.inputs if next((f for f in self.reg.fields(self.reg.tools[r.tool_id], r.mode) if f["id"] == k), {}).get("type") != "text"])
        all_used = n_numbers > 0 and n_assigned >= n_numbers
        in_top2 = r.tool_id in [t for t, _ in sl[:2]]
        if not r.inputs:
            conf = 0.35 if tool_clear else 0.2
        elif not r.missing and tool_clear:
            conf = 0.9
        elif not r.missing:
            conf = 0.65
        else:
            conf = 0.5 if tool_clear else 0.3
        if not r.missing and all_used and in_top2:
            conf = max(conf, 0.8)
        return RuleResult(r, conf, sl, "rules")

    def _target_words(self, question: str) -> set[str]:
        t = T.normalise(question)
        m = re.search(r"(?:find|calculate|compute|determine|what is|what's|get)\s+(?:the\s+)?([a-z ]{2,25}?)(?:\s+(?:of|if|when|given|for|from|with|where|using)\b|[,.?]|$)", t)
        return set(T.tokens(m.group(1))) if m else set()

    # ---- formula finder (deterministic) ------------------------------------------------------------
    def find_formulas(self, query: str, k: int = 6) -> list[dict]:
        qt = [w for w in T.tokens(query) if not re.fullmatch(r"[-+]?\d+(\.\d+)?", w)]
        if not qt:
            return []
        results: list[tuple[float, dict]] = []
        for tid, tool in self.reg.tools.items():
            base = set(T.tokens(tool["name"] + " " + tool.get("keywords", "")))
            ftoks = set(T.tokens(tool.get("formula", "")))
            for mk, m in tool["modes"].items():
                mt = set(T.tokens(m["label"]))
                s = 0.0
                for w in qt:
                    if w in mt:
                        s += 3.0
                    if w in base:
                        s += 1.5 * self.idf.get(w, 1.0)
                    if w in ftoks:
                        s += 0.7
                if s > 0:
                    ch = self.reg.chapter_for(tool)
                    results.append((s, {
                        "tool_id": tid, "tool_name": tool["name"], "mode": mk, "mode_label": m["label"],
                        "formula": tool.get("formula", "")[:240], "url": tool["url"],
                        "chapter": {"url": ch["url"], "title": ch["title"]} if ch else None,
                    }))
        results.sort(key=lambda x: -x[0])
        seen: set[tuple[str, str]] = set()
        out: list[dict] = []
        for s, r in results:
            key = (r["tool_id"], r["formula"][:40])
            if key in seen:
                continue
            seen.add(key)
            r["score"] = round(s, 2)
            out.append(r)
            if len(out) >= k:
                break
        return out

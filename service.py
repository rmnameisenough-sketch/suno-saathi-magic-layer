"""The Magic Layer brain. No web framework in here, so it can be tested directly.

Order of preference, always:
   1. deterministic rules / templates  (free, instant, works offline)
   2. AI help                          (only when rules are unsure or an explanation is requested)
   3. back to rules / templates        (when AI is over quota, down, or fails a safety check)

The calculators themselves compute every number. The AI never calculates.
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from collections import defaultdict, deque

from . import fallback, guard, prompts
from .config import Settings
from .providers.base import AIProvider
from .providers.chain import AllProvidersUnavailable, ProviderChain
from .quota import COSTS, QuotaManager
from .registry import Registry, RouteError
from .rules import CONVERSIONS, RuleEngine
from .text import extract_numbers

log = logging.getLogger("magic")
RULES_CONFIDENT = 0.75
WEAK_SHORTLIST = 5.0              # keyword score below this = rules are guessing, so the AI gets to see every tool
SHOW_RULES_ROUTE_ABOVE = 0.5      # below this a rules route is only offered as suggestions, never prefilled
REQUESTS_PER_MINUTE = 90          # light abuse limit for ALL requests (AI or not)


class ServiceError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status = status
        self.code = code


def build_providers(s: Settings) -> list[AIProvider]:
    from .providers.gemini import GeminiProvider
    from .providers.mock import MockProvider
    from .providers.openai_compat import OpenAICompatProvider
    out: list[AIProvider] = []
    for name in s.ai_providers:
        if name == "gemini":
            out.append(GeminiProvider(s.gemini_api_key, s.gemini_model, s.gemini_base_url, s.provider_timeout_s, s.gemini_thinking_budget))
        elif name == "openai_compat":
            out.append(OpenAICompatProvider(s.openai_compat_api_key, s.openai_compat_base_url, s.openai_compat_model, s.provider_timeout_s))
        elif name == "mock" and s.enable_mock_provider:
            out.append(MockProvider())
    return out


class MagicService:
    def __init__(self, settings: Settings, registry: Registry, chain: ProviderChain, quota: QuotaManager, now=time.time):
        self.s = settings
        self.reg = registry
        self.chain = chain
        self.quota = quota
        self.rules = RuleEngine(registry)
        self.now = now
        self.stats: dict[str, int] = defaultdict(int)
        self._req: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    # ---- input handling -----------------------------------------------------------------------------
    def _lang(self, body: dict) -> str:
        return "hi" if str(body.get("lang", "en")).lower().startswith("hi") else "en"

    def _text(self, body: dict, key: str, limit: int, required: bool = True) -> str:
        v = body.get(key, "")
        if not isinstance(v, str):
            raise ServiceError(400, "bad_request")
        v = re.sub(r"[\x00-\x08\x0b-\x1f]", " ", v).strip()
        if required and not v:
            raise ServiceError(400, "bad_request")
        if len(v) > limit:
            raise ServiceError(413, "too_long")
        return v

    def _check_rate(self, user) -> None:
        key = user.ip_key or user.id
        t = self.now()
        with self._lock:
            q = self._req[key]
            while q and t - q[0] > 60:
                q.popleft()
            if len(q) >= REQUESTS_PER_MINUTE:
                raise ServiceError(429, "rate_limit")
            q.append(t)

    def _usage(self, user) -> dict:
        u = self.quota.usage(user)
        u["ai_available"] = self.chain.unavailable_reason() is None
        return u

    # ---- AI attempt wrapper (reserve -> call -> refund on failure) ---------------------------------------
    def _try_ai(self, user, kind: str, req):
        """Returns (response_or_None, degraded_reason_or_None). Charges credits only on success."""
        reason = self.chain.unavailable_reason()
        if reason:
            self.stats["ai_skipped_" + reason] += 1
            return None, reason
        cost = COSTS[kind]
        d = self.quota.reserve(user, cost)
        if not d.allowed:
            self.stats["ai_denied_" + str(d.reason)] += 1
            return None, d.reason
        try:
            resp = self.chain.generate(req)
            self.stats["ai_ok"] += 1
            return resp, None
        except AllProvidersUnavailable as e:
            self.quota.refund(user, cost)
            self.stats["ai_fail_" + e.reason] += 1
            log.warning("AI unavailable: %s %s", e.reason, e.attempts)
            return None, e.reason

    def _refund(self, user, kind: str) -> None:
        self.quota.refund(user, COSTS[kind])

    # ---- ROUTE ------------------------------------------------------------------------------------------
    def route(self, user, body: dict) -> dict:
        self._check_rate(user)
        self.stats["route"] += 1
        q = self._text(body, "question", self.s.max_question_chars)
        lang = self._lang(body)
        rr = self.rules.route(q)
        suggestions = [self._suggest(tid) for tid, _ in rr.shortlist[:3]]
        out = {"ok": True, "source": "none", "route": None, "suggestions": suggestions, "confidence": rr.confidence,
               "degraded_reason": None, "notice": "", "warnings": []}
        if rr.route and rr.confidence >= RULES_CONFIDENT and not rr.route.missing:
            out.update(source="rules", route=rr.route.as_dict())
            out["usage"] = self._usage(user)
            return out

        ai_route, reason, warnings = None, None, []
        ids = [tid for tid, _ in rr.shortlist[:5]]
        if not rr.shortlist or rr.shortlist[0][1] < WEAK_SHORTLIST:
            ids = list(self.reg.tools)           # keywords found nothing useful: let the AI see every tool (about 5k tokens)
        req = prompts.build_route_request(q, lang, self.reg.describe_for_prompt(ids))
        resp, reason = self._try_ai(user, "route", req)
        if resp:
            ai_route, warnings = self._validate_ai_route(resp.text, q, ids)
            if not ai_route:
                self._refund(user, "route")
                reason = "guard_failed"

        if ai_route:
            out.update(source="ai", route=ai_route.as_dict(), warnings=warnings)
        elif rr.route and rr.confidence >= SHOW_RULES_ROUTE_ABOVE:
            out.update(source="rules", route=rr.route.as_dict(), degraded_reason=reason)
        else:
            out.update(source="none", degraded_reason=reason)
        if reason:
            out["notice"] = fallback.notice(lang, reason)
        out["usage"] = self._usage(user)
        return out

    def _suggest(self, tool_id: str) -> dict:
        t = self.reg.tools[tool_id]
        return {"tool_id": tool_id, "name": t["name"], "url": t["url"], "category": t["category"]}

    def _validate_ai_route(self, text: str, question: str, allowed_ids: list[str]):
        obj = prompts.parse_json_object(text)
        if not obj or not obj.get("tool_id"):
            return None, []
        tid = str(obj["tool_id"])
        if tid not in allowed_ids:
            return None, []
        inputs = obj.get("inputs") if isinstance(obj.get("inputs"), dict) else {}
        selects = obj.get("selects") if isinstance(obj.get("selects"), dict) else {}
        warnings: list[str] = []
        # The AI must not invent numbers: every value has to come from the question (allowing unit conversion).
        q_nums = extract_numbers(question)
        factors = {1.0} | set(CONVERSIONS.values())
        clean: dict = {}
        for k, v in inputs.items():
            if isinstance(v, str) and not re.fullmatch(r"[-+]?\d+(\.\d+)?(e[-+]?\d+)?", v.strip(), re.I):
                if v.strip().lower() in question.lower():          # chemical formula typed by the student
                    clean[k] = v
                else:
                    warnings.append(f"dropped {k}")
                continue
            try:
                num = float(v)
            except (TypeError, ValueError):
                warnings.append(f"dropped {k}")
                continue
            if any(math.isclose(num, n * f, rel_tol=1e-6, abs_tol=1e-12) for n in q_nums for f in factors):
                clean[k] = num
            else:
                warnings.append(f"dropped {k}")
        try:
            route = self.reg.validate_route(tid, obj.get("mode"), clean, selects)
        except RouteError:
            return None, []
        return route, warnings

    # ---- EXPLAIN / STEPS -----------------------------------------------------------------------------------
    def explain(self, user, body: dict) -> dict:
        self._check_rate(user)
        self.stats["explain"] += 1
        lang = self._lang(body)
        kind = "steps" if body.get("kind") == "steps" else "explain"
        result_text = self._text(body, "result_text", self.s.max_result_chars)
        if not any(c.isdigit() for c in result_text):
            raise ServiceError(400, "bad_request")
        try:
            route = self.reg.validate_route(str(body.get("tool_id", "")), body.get("mode", ""),
                                            body.get("inputs") if isinstance(body.get("inputs"), dict) else {},
                                            body.get("selects") if isinstance(body.get("selects"), dict) else {})
        except RouteError:
            raise ServiceError(400, "bad_request")
        tool = self.reg.tool(route.tool_id)
        labels = {f["id"]: f["label"] for f in self.reg.fields(tool, route.mode)}
        inputs = [{"label": labels.get(k, k), "value": v} for k, v in route.inputs.items()]
        formula = self.reg.formula_for(tool)
        template = (fallback.steps(lang, result_text) if kind == "steps"
                    else fallback.explain(lang, route.tool_name, route.mode_label, formula, inputs, result_text))
        ctx = {"language": lang, "tool": route.tool_name, "mode": route.mode_label, "formula": formula,
               "inputs": inputs, "calculator_output": result_text}
        resp, reason = self._try_ai(user, kind, prompts.build_explain_request(kind, lang, ctx))
        text, source, provider = template, "template", None
        if resp:
            g = guard.check_explanation(resp.text, json.dumps(ctx, ensure_ascii=False), lang)
            if g.ok:
                text, source, provider = resp.text.strip(), "ai", resp.provider
            else:
                self._refund(user, kind)
                self.stats["guard_fail_" + g.reason.split(":")[0]] += 1
                reason = "guard_failed"
        out = {"ok": True, "text": text, "source": source, "provider": provider, "kind": kind,
               "degraded_reason": reason, "notice": fallback.notice(lang, reason),
               "next": self._next(tool), "usage": self._usage(user)}
        return out

    def _next(self, tool: dict) -> dict:
        ch = self.reg.chapter_for(tool)
        return {"related": [{"tool_id": t["id"], "name": t["name"], "url": t["url"]} for t in self.reg.related_tools(tool)[:4]],
                "chapter": {"url": ch["url"], "title": ch["title"]} if ch else None}

    # ---- FORMULA FINDER ----------------------------------------------------------------------------------------
    def formula(self, user, body: dict) -> dict:
        self._check_rate(user)
        self.stats["formula"] += 1
        lang = self._lang(body)
        q = self._text(body, "query", self.s.max_question_chars)
        formulas = self.rules.find_formulas(q, 6)
        out = {"ok": True, "formulas": formulas, "summary": "", "source": "rules", "degraded_reason": None, "notice": ""}
        if formulas and body.get("use_ai") is True:
            ctx = {"language": lang, "student_question": q, "CANDIDATES": [
                {"tool": f["tool_name"], "mode": f["mode_label"], "formula": f["formula"]} for f in formulas[:4]]}
            resp, reason = self._try_ai(user, "formula", prompts.build_formula_request(lang, ctx))
            if resp:
                g = guard.check_explanation(resp.text, json.dumps(ctx, ensure_ascii=False), lang)
                if g.ok:
                    out.update(summary=resp.text.strip(), source="ai")
                else:
                    self._refund(user, "formula")
                    reason = "guard_failed"
            if reason:
                out["degraded_reason"], out["notice"] = reason, fallback.notice(lang, reason)
        out["usage"] = self._usage(user)
        return out

    # ---- misc ---------------------------------------------------------------------------------------------------------
    def usage(self, user) -> dict:
        return self._usage(user)

    def health(self) -> dict:
        return {"status": "ok", "env": self.s.env, "registry_tools": len(self.reg.tools),
                "ai_enabled": self.chain.has_providers(), "providers": self.chain.status(), "stats": dict(self.stats)}

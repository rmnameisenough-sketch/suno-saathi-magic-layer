"""Usage limits and credits.

Rules:
  * Only AI calls cost credits. Template answers and the normal calculators are free and unlimited
    (apart from a small per-minute abuse limit).
  * Credits are reserved BEFORE calling the AI and refunded if the AI was not actually used
    (provider down, bad output...). Users never pay for failures.
  * Every tier has a per-day allowance and a per-minute burst limit.
  * A global daily ceiling protects the provider's free quota. Free + anonymous users may use at
    most `free_share` of it, so premium users keep working when free users are using their share.

The UsageStore interface is the only thing that touches storage. MemoryUsageStore and
SqliteUsageStore are included; a Postgres/Supabase store can be added later without changing
anything else. (On free hosts the local disk is wiped on restart, so counters in SQLite reset
there; use an external database when this matters.)
"""
from __future__ import annotations

import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Settings


@dataclass(frozen=True)
class Tier:
    name: str
    daily: int
    per_minute: int


def tiers_from(settings: Settings) -> dict[str, Tier]:
    return {
        "anonymous": Tier("anonymous", settings.anon_daily, settings.anon_per_minute),
        "free": Tier("free", settings.free_daily, settings.free_per_minute),
        "premium": Tier("premium", settings.premium_daily, settings.premium_per_minute),
    }


# What each kind of AI task costs, in credits.
COSTS = {"route": 1, "explain": 1, "steps": 2, "formula": 1}

# Anonymous users are identified by browser id + IP, and a browser id is easy to change. So anonymous
# traffic from one IP address also shares a larger cap (this many times the anonymous daily allowance).
# It is generous on purpose: a school or a mobile network can put many real students behind one IP.
ANON_IP_MULTIPLIER = 6


class UsageStore(ABC):
    @abstractmethod
    def user_used(self, user_id: str, day: str) -> int: ...
    @abstractmethod
    def user_add(self, user_id: str, day: str, units: int) -> int: ...
    @abstractmethod
    def global_used(self, day: str, bucket: str) -> int: ...
    @abstractmethod
    def global_add(self, day: str, bucket: str, units: int) -> int: ...


class MemoryUsageStore(UsageStore):
    def __init__(self):
        self._u: dict[tuple[str, str], int] = defaultdict(int)
        self._g: dict[tuple[str, str], int] = defaultdict(int)

    def user_used(self, user_id, day): return self._u[(user_id, day)]
    def user_add(self, user_id, day, units):
        self._u[(user_id, day)] = max(0, self._u[(user_id, day)] + units)
        return self._u[(user_id, day)]
    def global_used(self, day, bucket): return self._g[(day, bucket)]
    def global_add(self, day, bucket, units):
        self._g[(day, bucket)] = max(0, self._g[(day, bucket)] + units)
        return self._g[(day, bucket)]


class SqliteUsageStore(UsageStore):
    def __init__(self, path: str = ":memory:"):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("CREATE TABLE IF NOT EXISTS user_usage (user_id TEXT, day TEXT, units INTEGER, PRIMARY KEY (user_id, day))")
            self._db.execute("CREATE TABLE IF NOT EXISTS global_usage (day TEXT, bucket TEXT, units INTEGER, PRIMARY KEY (day, bucket))")
            self._db.commit()

    def _get(self, sql, args):
        with self._lock:
            row = self._db.execute(sql, args).fetchone()
        return int(row[0]) if row else 0

    def _add(self, table, keys, units):
        with self._lock:
            cols = "user_id, day" if table == "user_usage" else "day, bucket"
            self._db.execute(f"INSERT INTO {table} ({cols}, units) VALUES (?, ?, 0) ON CONFLICT({cols}) DO NOTHING", keys)
            self._db.execute(f"UPDATE {table} SET units = MAX(0, units + ?) WHERE {cols.split(', ')[0]} = ? AND {cols.split(', ')[1]} = ?", (units, *keys))
            self._db.commit()
            row = self._db.execute(f"SELECT units FROM {table} WHERE {cols.split(', ')[0]} = ? AND {cols.split(', ')[1]} = ?", keys).fetchone()
        return int(row[0])

    def user_used(self, user_id, day): return self._get("SELECT units FROM user_usage WHERE user_id=? AND day=?", (user_id, day))
    def user_add(self, user_id, day, units): return self._add("user_usage", (user_id, day), units)
    def global_used(self, day, bucket): return self._get("SELECT units FROM global_usage WHERE day=? AND bucket=?", (day, bucket))
    def global_add(self, day, bucket, units): return self._add("global_usage", (day, bucket), units)


@dataclass
class Decision:
    allowed: bool
    reason: str | None = None        # user_daily | rate_limit | global_budget
    limit: int = 0
    used: int = 0
    remaining: int = 0
    reset_at: str = ""
    retry_after_s: int = 0


class QuotaManager:
    def __init__(self, settings: Settings, store: UsageStore | None = None, now=time.time):
        self.s = settings
        self.tiers = tiers_from(settings)
        self.store = store or (SqliteUsageStore(settings.usage_db) if settings.usage_db != ":memory:" else MemoryUsageStore())
        self.now = now
        self.tz = ZoneInfo(settings.quota_timezone)
        self._recent: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    # ---- helpers --------------------------------------------------------------------------
    def _day(self) -> str:
        return datetime.fromtimestamp(self.now(), self.tz).date().isoformat()

    def _reset_at(self) -> str:
        cur = datetime.fromtimestamp(self.now(), self.tz)
        return (cur + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    def _tier(self, user) -> Tier:
        return self.tiers.get(user.tier, self.tiers["anonymous"])

    def _bucket(self, user) -> str:
        return "premium" if user.tier == "premium" else "free"

    # ---- public API -----------------------------------------------------------------------------
    def usage(self, user) -> dict:
        tier = self._tier(user)
        day = self._day()
        used = self.store.user_used(user.id, day)
        return {"tier": tier.name, "daily_limit": tier.daily, "used": used, "remaining": max(0, tier.daily - used),
                "resets_at": self._reset_at()}

    def reserve(self, user, cost: int) -> Decision:
        tier = self._tier(user)
        with self._lock:
            day = self._day()
            t = self.now()
            q = self._recent[user.id]
            while q and t - q[0] > 60:
                q.popleft()
            used = self.store.user_used(user.id, day)
            base = Decision(True, None, tier.daily, used, max(0, tier.daily - used), self._reset_at())
            if len(q) >= tier.per_minute:
                base.allowed, base.reason, base.retry_after_s = False, "rate_limit", max(1, int(60 - (t - q[0])))
                return base
            if used + cost > tier.daily:
                base.allowed, base.reason = False, "user_daily"
                return base
            ip_id = ("ip:" + user.ip_key) if (user.tier == "anonymous" and getattr(user, "ip_key", "")) else ""
            if ip_id and self.store.user_used(ip_id, day) + cost > tier.daily * ANON_IP_MULTIPLIER:
                base.allowed, base.reason = False, "user_daily"
                return base
            free_used = self.store.global_used(day, "free")
            prem_used = self.store.global_used(day, "premium")
            free_cap = int(self.s.global_daily * self.s.free_share)
            if self._bucket(user) == "free" and free_used + cost > free_cap:
                base.allowed, base.reason = False, "global_budget"
                return base
            if free_used + prem_used + cost > self.s.global_daily:
                base.allowed, base.reason = False, "global_budget"
                return base
            q.append(t)
            new_used = self.store.user_add(user.id, day, cost)
            if ip_id:
                self.store.user_add(ip_id, day, cost)
            self.store.global_add(day, self._bucket(user), cost)
            base.used, base.remaining = new_used, max(0, tier.daily - new_used)
            return base

    def refund(self, user, cost: int) -> None:
        with self._lock:
            day = self._day()
            self.store.user_add(user.id, day, -cost)
            if user.tier == "anonymous" and getattr(user, "ip_key", ""):
                self.store.user_add("ip:" + user.ip_key, day, -cost)
            self.store.global_add(day, self._bucket(user), -cost)
            q = self._recent[user.id]
            if q:
                q.pop()

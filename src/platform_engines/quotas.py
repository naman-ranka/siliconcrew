"""Per-user quotas + abuse limits (Phase 2, slice 4).

The real risk in this workload is not raw demand — it is a user retry-looping a
minutes-long, memory-heavy synth job. So the caps that matter are:

  * **concurrency:** 1 in-flight synth job per user (the headline guard);
  * **rate:** synth runs/day;
  * **cost:** compute-minutes/month.

``QuotaManager`` enforces all three around a reserve/release pair. The counters
live behind a ``QuotaStore`` so a single process uses the in-memory store and a
horizontally-scaled deployment swaps in a shared (Postgres/Redis) store with the
same interface — concurrency across replicas needs that shared store to be real.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Protocol, Tuple


@dataclass(frozen=True)
class QuotaPolicy:
    synth_runs_per_day: int
    compute_minutes_per_month: int
    max_concurrent_synth: int


# Anonymous trial cannot synth at all (gated earlier by identity.authorize too);
# signed-in users get sensible hosted-tier caps. Tune via config at deploy time.
DEFAULT_POLICIES: Dict[str, QuotaPolicy] = {
    "anonymous": QuotaPolicy(synth_runs_per_day=0, compute_minutes_per_month=0, max_concurrent_synth=0),
    "user": QuotaPolicy(synth_runs_per_day=20, compute_minutes_per_month=600, max_concurrent_synth=1),
}


class QuotaExceeded(Exception):
    """Raised when a reservation would exceed a cap. Carries the error envelope."""

    def __init__(self, code: str, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_envelope(self) -> dict:
        return {"ok": False, "error": {"code": self.code, "message": self.message, "details": self.details}}


class QuotaStore(Protocol):
    """Counter storage. Implementations must make the concurrency ops atomic."""

    def get_day_count(self, user_id: str, day_key: str) -> int: ...
    def incr_day_count(self, user_id: str, day_key: str) -> None: ...
    def get_month_minutes(self, user_id: str, month_key: str) -> float: ...
    def add_month_minutes(self, user_id: str, month_key: str, minutes: float) -> None: ...
    def try_acquire_concurrency(self, user_id: str, limit: int) -> bool: ...
    def release_concurrency(self, user_id: str) -> None: ...
    def get_concurrency(self, user_id: str) -> int: ...


class InMemoryQuotaStore:
    """Thread-safe single-process store (tests / single Cloud Run instance)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._days: Dict[Tuple[str, str], int] = {}
        self._months: Dict[Tuple[str, str], float] = {}
        self._concurrency: Dict[str, int] = {}

    def get_day_count(self, user_id, day_key):
        with self._lock:
            return self._days.get((user_id, day_key), 0)

    def incr_day_count(self, user_id, day_key):
        with self._lock:
            self._days[(user_id, day_key)] = self._days.get((user_id, day_key), 0) + 1

    def get_month_minutes(self, user_id, month_key):
        with self._lock:
            return self._months.get((user_id, month_key), 0.0)

    def add_month_minutes(self, user_id, month_key, minutes):
        with self._lock:
            self._months[(user_id, month_key)] = self._months.get((user_id, month_key), 0.0) + minutes

    def try_acquire_concurrency(self, user_id, limit):
        with self._lock:
            cur = self._concurrency.get(user_id, 0)
            if cur >= limit:
                return False
            self._concurrency[user_id] = cur + 1
            return True

    def release_concurrency(self, user_id):
        with self._lock:
            cur = self._concurrency.get(user_id, 0)
            if cur > 0:
                self._concurrency[user_id] = cur - 1

    def get_concurrency(self, user_id):
        with self._lock:
            return self._concurrency.get(user_id, 0)


class PostgresQuotaStore:
    """Shared quota counters in Cloud SQL — caps survive horizontal scaling.

    The concurrency acquire is the critical one: it must be atomic across
    replicas. We do it inside a single transaction with ``SELECT ... FOR UPDATE``
    so concurrent acquires on the same user serialize on the row lock — only one
    instance can take the last slot. psycopg is lazy; ``connect`` is injectable
    for tests.
    """

    def __init__(self, dsn: str, connect=None):
        self._dsn = dsn
        self._connect_fn = connect

    def _connect(self):
        if self._connect_fn is not None:
            return self._connect_fn(self._dsn)
        import psycopg  # lazy

        return psycopg.connect(self._dsn)

    def init_schema(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS quota_concurrency ("
                "user_id TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0)"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS quota_daily ("
                "user_id TEXT, day TEXT, count INTEGER NOT NULL DEFAULT 0, "
                "PRIMARY KEY (user_id, day))"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS quota_monthly ("
                "user_id TEXT, month TEXT, minutes DOUBLE PRECISION NOT NULL DEFAULT 0, "
                "PRIMARY KEY (user_id, month))"
            )
            conn.commit()

    def try_acquire_concurrency(self, user_id, limit):
        # One transaction: ensure the row exists, lock it FOR UPDATE, then test +
        # increment. The row lock is what makes this atomic across replicas.
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO quota_concurrency (user_id, count) VALUES (%s, 0) "
                "ON CONFLICT (user_id) DO NOTHING",
                (user_id,),
            )
            cur.execute("SELECT count FROM quota_concurrency WHERE user_id = %s FOR UPDATE", (user_id,))
            row = cur.fetchone()
            current = row[0] if row else 0
            if current >= limit:
                conn.commit()
                return False
            cur.execute("UPDATE quota_concurrency SET count = count + 1 WHERE user_id = %s", (user_id,))
            conn.commit()
            return True

    def release_concurrency(self, user_id):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE quota_concurrency SET count = GREATEST(count - 1, 0) WHERE user_id = %s",
                (user_id,),
            )
            conn.commit()

    def get_concurrency(self, user_id):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count FROM quota_concurrency WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return row[0] if row else 0

    def get_day_count(self, user_id, day_key):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count FROM quota_daily WHERE user_id = %s AND day = %s", (user_id, day_key))
            row = cur.fetchone()
            return row[0] if row else 0

    def incr_day_count(self, user_id, day_key):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO quota_daily (user_id, day, count) VALUES (%s, %s, 1) "
                "ON CONFLICT (user_id, day) DO UPDATE SET count = quota_daily.count + 1",
                (user_id, day_key),
            )
            conn.commit()

    def get_month_minutes(self, user_id, month_key):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT minutes FROM quota_monthly WHERE user_id = %s AND month = %s", (user_id, month_key))
            row = cur.fetchone()
            return float(row[0]) if row else 0.0

    def add_month_minutes(self, user_id, month_key, minutes):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO quota_monthly (user_id, month, minutes) VALUES (%s, %s, %s) "
                "ON CONFLICT (user_id, month) DO UPDATE SET minutes = quota_monthly.minutes + %s",
                (user_id, month_key, minutes, minutes),
            )
            conn.commit()


def build_quota_manager(settings) -> "QuotaManager":
    """Pick the quota store from settings: shared Postgres in hosted mode."""
    if settings.persistence_engine == "postgres" and settings.database_url:
        store = PostgresQuotaStore(settings.database_url)
        try:
            store.init_schema()
        except Exception:
            pass  # schema may already exist / be created out-of-band
        return QuotaManager(store=store)
    return QuotaManager(store=InMemoryQuotaStore())


@dataclass
class SynthReservation:
    user_id: str
    day_key: str
    month_key: str
    started_at: float


class QuotaManager:
    """Enforce per-user synth concurrency, daily run, and monthly compute caps."""

    def __init__(self, store: Optional[QuotaStore] = None, policies=None, clock=time.time):
        self._store = store or InMemoryQuotaStore()
        self._policies = policies or DEFAULT_POLICIES
        self._clock = clock

    def policy_for(self, tier: str) -> QuotaPolicy:
        return self._policies.get(tier, self._policies["user"])

    def _keys(self) -> Tuple[str, str]:
        t = time.gmtime(self._clock())
        return (time.strftime("%Y-%m-%d", t), time.strftime("%Y-%m", t))

    def reserve_synth_run(self, user_id: str, tier: str = "user") -> SynthReservation:
        """Atomically check all caps and reserve a synth slot, or raise.

        Order matters: take the concurrency slot first (the tightest, atomic
        guard against retry-loops), then validate rate/cost; release the slot if
        a softer cap fails so we never leak concurrency.
        """
        policy = self.policy_for(tier)
        day_key, month_key = self._keys()

        if policy.max_concurrent_synth <= 0:
            raise QuotaExceeded(
                "synth_not_allowed",
                f"Tier '{tier}' may not start synthesis runs.",
                {"tier": tier},
            )

        if not self._store.try_acquire_concurrency(user_id, policy.max_concurrent_synth):
            raise QuotaExceeded(
                "concurrency_limit",
                f"You already have {policy.max_concurrent_synth} synthesis run(s) in flight. "
                "Wait for it to finish before starting another.",
                {"max_concurrent": policy.max_concurrent_synth},
            )

        try:
            day_count = self._store.get_day_count(user_id, day_key)
            if day_count >= policy.synth_runs_per_day:
                raise QuotaExceeded(
                    "daily_run_limit",
                    f"Daily synthesis limit reached ({policy.synth_runs_per_day}/day).",
                    {"limit": policy.synth_runs_per_day, "used": day_count},
                )
            used_minutes = self._store.get_month_minutes(user_id, month_key)
            if used_minutes >= policy.compute_minutes_per_month:
                raise QuotaExceeded(
                    "monthly_compute_limit",
                    f"Monthly compute budget exhausted ({policy.compute_minutes_per_month} min).",
                    {"limit": policy.compute_minutes_per_month, "used": round(used_minutes, 2)},
                )
        except QuotaExceeded:
            self._store.release_concurrency(user_id)
            raise

        self._store.incr_day_count(user_id, day_key)
        return SynthReservation(user_id, day_key, month_key, self._clock())

    def release_synth_run(self, reservation: SynthReservation, compute_minutes: Optional[float] = None) -> None:
        """Release the concurrency slot and bill compute minutes (measured or elapsed)."""
        if compute_minutes is None:
            compute_minutes = max(0.0, (self._clock() - reservation.started_at) / 60.0)
        self._store.add_month_minutes(reservation.user_id, reservation.month_key, compute_minutes)
        self._store.release_concurrency(reservation.user_id)

    def usage(self, user_id: str, tier: str = "user") -> dict:
        day_key, month_key = self._keys()
        policy = self.policy_for(tier)
        return {
            "runs_today": self._store.get_day_count(user_id, day_key),
            "runs_per_day": policy.synth_runs_per_day,
            "compute_minutes_month": round(self._store.get_month_minutes(user_id, month_key), 2),
            "compute_minutes_limit": policy.compute_minutes_per_month,
            "concurrent_synth": self._store.get_concurrency(user_id),
            "max_concurrent_synth": policy.max_concurrent_synth,
        }

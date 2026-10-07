"""Single budgeted model gateway.

Every model call in the app goes through here. It reserves the registered
envelope before sending, records reconciled usage, and refuses to call when the
daily/monthly token or USD ceilings would be exceeded. Failure degrades to the
caller (local mode) - there is never a silent provider fallback.
"""
import json
import os
import threading
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

from . import operation_lock

BUDGET = Path("harness/budget.json")
# Runtime-state paths are relative to the user data directory (App Support on
# desktop, .local/app in a checkout), never to the read-only application bundle.
USAGE = Path("usage.jsonl")
# --- test mode -----------------------------------------------------------------
# Testing must not be blocked by (or consume) the owner-approved runtime ceilings.
# PDH_DEV=1 or a DEV_MODE file in the user data directory switches to a SEPARATE
# ledger and a separate, deliberately loose ceiling. The shipped runtime limits are
# untouched, and dev spend can never be mistaken for runtime usage.
DEV_MARKER = Path("DEV_MODE")
DEV_LEDGER = Path("usage-dev.jsonl")
DEV_POLICY = {"daily_total_tokens": 5_000_000, "monthly_total_tokens": 50_000_000,
              "daily_usd": "10.00", "monthly_usd": "50.00"}
# Owner-facing kill switch: while this marker exists every call returns degraded
# before admission, so no request (not even a dry-run reservation) is made.
AI_DISABLED_MARKER = Path("AI_DISABLED")
ENV_FILE = Path(".local/deepseek.env")
KEY_FILE_NAME = "deepseek.env"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


def request_envelope(operation, model, max_output, messages):
    body = {"model": model, "thinking": {"type": "disabled"},
            "max_tokens": max_output, "messages": messages}
    if operation == "route_growth_judge":
        body.update({"temperature": 0, "response_format": {"type": "json_object"}})
    return body


def load_budget(root="."):
    return json.loads((Path(root) / BUDGET).read_text())


def dev_mode_enabled(root=".", data_dir=None):
    base = Path(data_dir) if data_dir else Path(root)
    return os.environ.get("PDH_DEV") == "1" or (base / DEV_MARKER).exists()


def _read_env_key(path):
    """Read DEEPSEEK_API_KEY from a KEY=value file; missing or unreadable is not an error."""
    try:
        if not path.is_file():
            return None
        for line in path.read_text().splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                value = line.split("=", 1)[1].strip()
                if value:
                    return value
    except OSError:
        return None
    return None


def _cost(provider, input_tokens, output_tokens, cache_hits=0):
    prices = provider["usd_per_million"]
    return ((input_tokens - cache_hits) * Decimal(str(prices["input_miss"]))
            + cache_hits * Decimal(str(prices["input_hit"]))
            + output_tokens * Decimal(str(prices["output"]))) / Decimal(1_000_000)


class BudgetExceeded(RuntimeError):
    pass


# Keep the existing process-wide thread admission guard as well as the
# resource-specific kernel lock used below for independent app processes.
_LEDGER_LOCK = threading.Lock()


def _reset_admission_lock_after_fork():
    global _LEDGER_LOCK
    _LEDGER_LOCK = threading.Lock()


os.register_at_fork(after_in_child=_reset_admission_lock_after_fork)


class Gateway:
    def __init__(self, root=".", ledger=USAGE, dev=None, data_dir=None):
        self.root = Path(root)
        # Runtime state (usage ledgers, dev marker, provider key) belongs to the
        # user data directory, never to the read-only application bundle.
        self.data_dir = Path(data_dir) if data_dir else self.root
        self.config = load_budget(root)
        self.dev = dev_mode_enabled(root, self.data_dir) if dev is None else bool(dev)
        self.ledger = self.data_dir / (DEV_LEDGER if self.dev else ledger)

    # ---------------------------------------------------------- provider key
    def key_file(self):
        """Writable location for the runtime provider key, inside the data dir."""
        return self.data_dir / KEY_FILE_NAME

    def _key_candidates(self):
        explicit = os.environ.get("PAPERDIGHELPER_KEY_FILE")
        if explicit:
            yield Path(explicit)
        yield self.key_file()
        if self.root != self.data_dir:
            # A checkout keeps the legacy key at <root>/.local/deepseek.env.
            yield self.root / ENV_FILE
        yield self.data_dir / ENV_FILE

    def _load_key(self):
        key = os.environ.get("DEEPSEEK_API_KEY")
        if key:
            return key, "environment"
        seen = set()
        for candidate in self._key_candidates():
            candidate = Path(candidate)
            if candidate in seen:
                continue
            seen.add(candidate)
            value = _read_env_key(candidate)
            if value:
                return value, str(candidate)
        return None, None

    def provider_status(self):
        """Configured state for the UI. Never returns the key itself."""
        key, source = self._load_key()
        return {
            "configured": bool(key),
            "source": source,
            "model": (self.config.get("provider") or {}).get("model"),
            "key_file": str(self.key_file()),
        }

    def save_key(self, value):
        value = (value or "").strip()
        if not value:
            raise ValueError("API key 不能为空")
        if len(value) > 512 or any(char in value for char in "\r\n"):
            raise ValueError("API key 格式无效")
        target = self.key_file()
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(target.parent, 0o700)
        except OSError:
            pass
        with target.open("w") as handle:
            handle.write(f"DEEPSEEK_API_KEY={value}\n")
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
        return self.provider_status()

    def clear_key(self):
        try:
            self.key_file().unlink()
        except FileNotFoundError:
            pass
        return self.provider_status()

    def limits(self):
        """Runtime ceilings by default; the separate dev ceilings only in test mode."""
        policy = dict(self.config["policy"])
        if self.dev:
            policy.update(DEV_POLICY)
        return policy

    # ------------------------------------------------------------ switch
    def enabled(self):
        return not (self.data_dir / AI_DISABLED_MARKER).exists()

    def set_enabled(self, enabled):
        marker = self.data_dir / AI_DISABLED_MARKER
        if enabled:
            try:
                marker.unlink()
            except FileNotFoundError:
                pass
        else:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("AI disabled by owner\n")
        return self.enabled()

    # ------------------------------------------------------------ accounting
    def _ledger_serial(self):
        # Resolve aliases before deriving the lock so every Gateway using the
        # same ledger joins the same cross-process admission/read/write section.
        ledger = self.ledger.resolve()
        return operation_lock.serial(ledger.parent, 'ledger:' + str(ledger))

    def _entries(self):
        """Effective ledger rows: one per legacy row or per reservation id.

        A reservation stays charged at its registered cap until a later row
        reconciles it (actual usage) or releases it (provider rejected before
        generation). Unknown usage therefore keeps the reservation.
        """
        with self._ledger_serial():
            if not self.ledger.exists():
                return []
            plain, by_id = [], {}
            for line in self.ledger.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                rid = entry.get("id")
                if not rid:
                    plain.append(entry)
                    continue
                current = by_id.get(rid)
                if current is None or current.get("status") in ("reserved", "unknown"):
                    if entry.get("status") == "unknown" and current is not None:
                        continue  # unknown keeps the reserved values
                    by_id[rid] = entry
            return plain + list(by_id.values())

    def _usage(self, day, month):
        """Return ((day_tokens, day_usd), (month_tokens, month_usd))."""
        with self._ledger_serial():
            day_tokens = month_tokens = 0
            day_usd = month_usd = Decimal(0)
            for entry in self._entries():
                tokens = int(entry.get("input", 0)) + int(entry.get("output", 0))
                usd = Decimal(str(entry.get("usd", "0")))
                if entry["date"] == day:
                    day_tokens, day_usd = day_tokens + tokens, day_usd + usd
                if entry["date"].startswith(month):
                    month_tokens, month_usd = month_tokens + tokens, month_usd + usd
            return (day_tokens, day_usd), (month_tokens, month_usd)

    def admit(self, operation, day, month):
        """Return reservation (input, output, usd) or raise BudgetExceeded."""
        with self._ledger_serial():
            provider = self.config["provider"]
            if provider is None:
                raise BudgetExceeded("no provider configured")
            op = self.config["operations"].get(operation)
            if op is None:
                raise BudgetExceeded(f"operation not registered: {operation}")
            if op.get("owner_approved") is False:
                raise BudgetExceeded(f"operation awaiting owner approval: {operation}")
            cap_in, cap_out = op["cap"]["input"], op["cap"]["output"]
            reserve_usd = _cost(provider, cap_in, cap_out)
            (day_tokens, day_usd), (month_tokens, month_usd) = self._usage(day, month)
            policy = self.limits()
            if day_tokens + cap_in + cap_out > policy["daily_total_tokens"]:
                raise BudgetExceeded(f"daily token ceiling ({day_tokens:,}/{policy['daily_total_tokens']:,} used)")
            if month_tokens + cap_in + cap_out > policy["monthly_total_tokens"]:
                raise BudgetExceeded(f"monthly token ceiling ({month_tokens:,}/{policy['monthly_total_tokens']:,} used)")
            if day_usd + reserve_usd > Decimal(str(policy["daily_usd"])):
                raise BudgetExceeded(f"daily USD ceiling (${day_usd:.4f}/${policy['daily_usd']} used)")
            if month_usd + reserve_usd > Decimal(str(policy["monthly_usd"])):
                raise BudgetExceeded(f"monthly USD ceiling (${month_usd:.4f}/${policy['monthly_usd']} used)")
            return cap_in, cap_out, reserve_usd

    def usage_today(self):
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        (tokens, usd), (month_tokens, month_usd) = self._usage(today, today[:7])
        return {"tokens": tokens, "usd": str(usd), "month_tokens": month_tokens, "month_usd": str(month_usd),
                "ceiling": self.limits()["daily_total_tokens"], "dev": self.dev, "enabled": self.enabled()}

    def _append(self, entry):
        with self._ledger_serial():
            self.ledger.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger.open("a") as handle:
                handle.write(json.dumps(entry) + "\n")

    def _record(self, date, operation, usage, usd, model, rid=None, status=None):
        entry = {
            "date": date, "operation": operation, "model": model,
            "input": usage.get("prompt_tokens", 0), "output": usage.get("completion_tokens", 0),
            "cache_hit": usage.get("prompt_cache_hit_tokens", 0),
            "total": usage.get("total_tokens", 0), "usd": str(usd),
        }
        if rid:
            entry.update({"id": rid, "status": status})
        self._append(entry)

    # -------------------------------------------------------------- provider
    def call(self, operation, messages, dry_run=False, timeout=90):
        """Call the runtime provider for a registered operation. Returns dict or None.

        One attempt only: no retry, no model fallback. The envelope is written to
        the ledger as an in-flight reservation before sending and is reconciled
        only when the provider reports usage.
        """
        import datetime
        import uuid
        if not self.enabled():
            return {"ok": False, "degraded": True, "disabled": True, "reason": "AI 已关闭"}
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        month = today[:7]
        provider = self.config["provider"]
        with _LEDGER_LOCK, self._ledger_serial():
            try:
                cap_in, cap_out, reserve_usd = self.admit(operation, today, month)
            except BudgetExceeded as exc:
                return {"ok": False, "degraded": True, "reason": str(exc)}
            try:
                body = json.dumps(request_envelope(operation, provider["model"], cap_out, messages),
                                  ensure_ascii=False).encode('utf-8')
            except (UnicodeError, TypeError, ValueError, RecursionError):
                return {"ok": False, "degraded": True, "invalid_input": True,
                        "usage_unknown": False, "reason": "invalid request text; nothing sent"}
            if dry_run:
                return {"ok": True, "dry_run": True, "operation": operation,
                        "reservation": {"input": cap_in, "output": cap_out, "usd": str(reserve_usd)}}
            key, _source = self._load_key()
            if not key:
                return {"ok": False, "degraded": True, "reason": "no API key"}
            rid = uuid.uuid4().hex
            self._record(today, operation, {"prompt_tokens": cap_in, "completion_tokens": cap_out},
                         reserve_usd, provider["model"], rid, "reserved")
        request = urllib.request.Request(
            DEEPSEEK_URL, data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                     "User-Agent": "PaperDigHelper/0.1 (local app)"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500:
                # Rejected before generation (auth, balance, validation, rate limit).
                self._record(today, operation, {}, Decimal(0), provider["model"], rid, "released")
            return {"ok": False, "degraded": True, "usage_unknown": not 400 <= exc.code < 500,
                    "http_status": exc.code, "reason": f"HTTPError: {exc.code}"}
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            # The request may have been processed: keep the reservation charged.
            return {"ok": False, "degraded": True, "usage_unknown": True,
                    "reason": f"{type(exc).__name__}: {exc}"}
        usage = payload.get("usage") if isinstance(payload, dict) else None
        model = (payload.get("model") if isinstance(payload, dict) else None) or provider["model"]
        content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content", "")
                   if isinstance(payload, dict) else "")
        finish_reason = ((payload.get('choices') or [{}])[0].get('finish_reason') if isinstance(payload, dict) else None)
        if not isinstance(usage, dict) or "prompt_tokens" not in usage or "completion_tokens" not in usage:
            self._record(today, operation, {"prompt_tokens": cap_in, "completion_tokens": cap_out},
                         reserve_usd, model, rid, "unknown")
            return {"ok": True, "content": content, 'finish_reason': finish_reason, "usage": {"total_tokens": cap_in + cap_out},
                    "usage_unknown": True, "usd": str(reserve_usd), "model": model, "dev": self.dev}
        usd = _cost(provider, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                    usage.get("prompt_cache_hit_tokens", 0))
        self._record(today, operation, usage, usd, model, rid, "reconciled")
        return {"ok": True, "content": content, 'finish_reason': finish_reason, "usage": usage, "usd": str(usd), "model": model, "dev": self.dev}

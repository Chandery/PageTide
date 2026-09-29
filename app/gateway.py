"""Single budgeted model gateway.

Every model call in the app goes through here. It reserves the registered
envelope before sending, records reconciled usage, and refuses to call when the
daily/monthly token or USD ceilings would be exceeded. Failure degrades to the
caller (local mode) - there is never a silent provider fallback.
"""
import json
import os
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

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
ENV_FILE = Path(".local/deepseek.env")
KEY_FILE_NAME = "deepseek.env"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


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

    # ------------------------------------------------------------ accounting
    def _entries(self, day, month):
        if not self.ledger.exists():
            return []
        entries = []
        for line in self.ledger.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry["date"] == day or entry["date"].startswith(month):
                entries.append(entry)
        return entries

    def _usage(self, day, month):
        entries = self._entries(day, month)
        tokens = sum(e["input"] + e["output"] for e in entries)
        usd = sum(Decimal(str(e["usd"])) for e in entries) if entries else Decimal(0)
        return tokens, usd

    def admit(self, operation, day, month):
        """Return reservation (input, output, usd) or raise BudgetExceeded."""
        provider = self.config["provider"]
        if provider is None:
            raise BudgetExceeded("no provider configured")
        op = self.config["operations"].get(operation)
        if op is None:
            raise BudgetExceeded(f"operation not registered: {operation}")
        cap_in, cap_out = op["cap"]["input"], op["cap"]["output"]
        reserve_usd = _cost(provider, cap_in, cap_out)
        tokens, usd = self._usage(day, month)
        policy = self.limits()
        if tokens + cap_in + cap_out > policy["daily_total_tokens"]:
            raise BudgetExceeded(f"daily token ceiling ({tokens:,}/{policy['daily_total_tokens']:,} used)")
        if tokens + cap_in + cap_out > policy["monthly_total_tokens"]:
            raise BudgetExceeded(f"monthly token ceiling ({tokens:,}/{policy['monthly_total_tokens']:,} used)")
        if usd + reserve_usd > Decimal(str(policy["daily_usd"])):
            raise BudgetExceeded(f"daily USD ceiling (${usd:.4f}/${policy['daily_usd']} used)")
        if usd + reserve_usd > Decimal(str(policy["monthly_usd"])):
            raise BudgetExceeded(f"monthly USD ceiling (${usd:.4f}/${policy['monthly_usd']} used)")
        return cap_in, cap_out, reserve_usd

    def usage_today(self):
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        tokens, usd = self._usage(today, today[:7])
        return {"tokens": tokens, "usd": str(usd), "ceiling": self.limits()["daily_total_tokens"], "dev": self.dev}

    def _record(self, date, operation, usage, usd, model):
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a") as handle:
            handle.write(json.dumps({
                "date": date, "operation": operation, "model": model,
                "input": usage.get("prompt_tokens", 0), "output": usage.get("completion_tokens", 0),
                "cache_hit": usage.get("prompt_cache_hit_tokens", 0),
                "total": usage.get("total_tokens", 0), "usd": str(usd),
            }) + "\n")

    # -------------------------------------------------------------- provider
    def call(self, operation, messages, dry_run=False, timeout=90):
        """Call the runtime provider for a registered operation. Returns dict or None."""
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        month = today[:7]
        try:
            cap_in, cap_out, reserve_usd = self.admit(operation, today, month)
        except BudgetExceeded as exc:
            return {"ok": False, "degraded": True, "reason": str(exc)}
        if dry_run:
            return {"ok": True, "dry_run": True, "operation": operation,
                    "reservation": {"input": cap_in, "output": cap_out, "usd": str(reserve_usd)}}
        key, _source = self._load_key()
        if not key:
            return {"ok": False, "degraded": True, "reason": "no API key"}
        provider = self.config["provider"]
        body = json.dumps({
            "model": provider["model"],
            "thinking": {"type": "disabled"},
            "max_tokens": cap_out,
            "messages": messages,
        }).encode()
        request = urllib.request.Request(
            DEEPSEEK_URL, data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                     "User-Agent": "PaperDigHelper/0.1 (local app)"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            return {"ok": False, "degraded": True, "reason": f"{type(exc).__name__}: {exc}"}
        usage = payload.get("usage", {})
        model = payload.get("model", provider["model"])
        usd = _cost(provider, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                    usage.get("prompt_cache_hit_tokens", 0))
        self._record(today, operation, usage, usd, model)
        content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        return {"ok": True, "content": content, "usage": usage, "usd": str(usd), "model": model, "dev": self.dev}

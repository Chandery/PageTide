"""Single budgeted model gateway.

Every model call in the app goes through here. It reserves the registered
envelope before sending, records reconciled usage, and refuses to call when the
daily/monthly token or USD ceilings would be exceeded. Failure degrades to the
caller (local mode) - there is never a silent provider fallback.
"""
import json
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

BUDGET = Path("harness/budget.json")
USAGE = Path(".local/app/usage.jsonl")
ENV_FILE = Path(".local/deepseek.env")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


def load_budget(root="."):
    return json.loads((Path(root) / BUDGET).read_text())


def _load_key():
    import os
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def _cost(provider, input_tokens, output_tokens, cache_hits=0):
    prices = provider["usd_per_million"]
    return ((input_tokens - cache_hits) * Decimal(str(prices["input_miss"]))
            + cache_hits * Decimal(str(prices["input_hit"]))
            + output_tokens * Decimal(str(prices["output"]))) / Decimal(1_000_000)


class BudgetExceeded(RuntimeError):
    pass


class Gateway:
    def __init__(self, root=".", ledger=USAGE):
        self.root = Path(root)
        self.config = load_budget(root)
        self.ledger = Path(root) / ledger

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
        policy = self.config["policy"]
        if tokens + cap_in + cap_out > policy["daily_total_tokens"]:
            raise BudgetExceeded("daily token ceiling")
        if tokens + cap_in + cap_out > policy["monthly_total_tokens"]:
            raise BudgetExceeded("monthly token ceiling")
        if usd + reserve_usd > Decimal(str(policy["daily_usd"])):
            raise BudgetExceeded("daily USD ceiling")
        if usd + reserve_usd > Decimal(str(policy["monthly_usd"])):
            raise BudgetExceeded("monthly USD ceiling")
        return cap_in, cap_out, reserve_usd

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
        key = _load_key()
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
        return {"ok": True, "content": content, "usage": usage, "usd": str(usd), "model": model}

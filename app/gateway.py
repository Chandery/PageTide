"""Single budgeted model gateway.

Every model call in the app goes through here. It reserves the registered
envelope before sending and records reconciled usage. Aggregate admission
limits are an explicit policy; per-request bounds always apply. Failure
degrades to the caller - there is never a silent provider fallback.
"""
import json
import copy
import base64
import http.client
import os
import re
import threading
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

from . import operation_lock, platform_compat

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
DEV_POLICY = {"aggregate_limits_enabled": True,
              "daily_total_tokens": 5_000_000, "monthly_total_tokens": 50_000_000,
              "daily_usd": "10.00", "monthly_usd": "50.00"}
# Owner-facing kill switch: while this marker exists every call returns degraded
# before admission, so no request (not even a dry-run reservation) is made.
AI_DISABLED_MARKER = Path("AI_DISABLED")
ENV_FILE = Path(".local/deepseek.env")
KEY_FILE_NAME = "deepseek.env"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
CONNECTION_TEST_OPERATION = 'ai_connection_test'
CONNECTION_TEST_MESSAGE = 'Reply only OK.'


def request_envelope(operation, model, max_output, messages):
    body = {"model": model, "thinking": {"type": "disabled"},
            "max_tokens": max_output, "messages": messages}
    if operation in {"daily_triage", "route_growth_judge", "project_guidance", "route_map_create",
                     "route_map_revision", "category_review"}:
        body.update({"temperature": 0, "response_format": {"type": "json_object"}})
    return body


def input_bound(envelope):
    """Bound the complete encoded text, including JSON and protocol framing.

    UTF-8 bytes are deliberately conservative, not a tokenizer parity claim.
    Inline image bytes are transport encoding, not text tokens: the documented
    DeepSeek Flash ceiling is 1024 tokens/image. No external image fetch or
    unregistered multimodal content is admitted. Unknown shapes fail closed.
    """
    counted = copy.deepcopy(envelope)
    images = 0
    messages = counted.get('messages')
    if not isinstance(messages, list):
        raise ValueError('messages must be a list')
    for message in messages:
        if not isinstance(message, dict) or set(message) != {'role', 'content'}:
            raise ValueError('invalid message fields')
        if message['role'] not in {'system', 'user', 'assistant'}:
            raise ValueError('invalid message role')
        content = message['content']
        if isinstance(content, str):
            continue
        if not isinstance(content, list) or message['role'] != 'user':
            raise ValueError('invalid message content')
        for part in content:
            if not isinstance(part, dict):
                raise ValueError('invalid content part')
            if part.get('type') == 'text' and set(part) == {'type', 'text'} and isinstance(part['text'], str):
                continue
            if (part.get('type') != 'image_url' or set(part) != {'type', 'image_url'}
                    or not isinstance(part['image_url'], dict) or set(part['image_url']) != {'url'}):
                raise ValueError('unsupported content part')
            url = part['image_url']['url']
            if (not isinstance(url, str) or not url.startswith(('data:image/png;base64,',
                    'data:image/jpeg;base64,', 'data:image/webp;base64,')) or len(url) > 8 * 1024 * 1024):
                raise ValueError('only bounded inline reader images are allowed')
            base64.b64decode(url.split(',', 1)[1], validate=True)
            part['image_url']['url'] = '[inline image]'
            images += 1
    if images > 1:
        raise ValueError('only one reader page image is allowed')
    return len(json.dumps(counted, ensure_ascii=False, allow_nan=False).encode('utf-8')) + 256 + 1024 * images


def load_budget(root="."):
    return json.loads((Path(root) / BUDGET).read_text(encoding="utf-8"))


def dev_mode_enabled(root=".", data_dir=None):
    base = Path(data_dir) if data_dir else Path(root)
    return os.environ.get("PDH_DEV") == "1" or (base / DEV_MARKER).exists()


def _read_env_key(path):
    """Read DEEPSEEK_API_KEY from a KEY=value file; missing or unreadable is not an error."""
    try:
        if not path.is_file():
            return None
        for line in path.read_text(encoding="utf-8").splitlines():
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


def _connection_tracking_failure(reservation=None, http_status=None):
    """Do not mistake a pre-send local write failure for an uncertain charge."""
    pending = reservation is not None
    result = {'ok': False, 'degraded': True, 'tracking_failed': True,
              'usage_unknown': pending, 'usage_reserved': pending,
              'reservation': reservation,
              'reason': ('local usage tracking failed after request; accounting reservation retained'
                         if pending else 'local usage tracking failed; nothing sent')}
    if http_status is not None:
        result['http_status'] = http_status
    return result


def _http_provider_error(error):
    """Classify one explicit 400 contract error; never return provider text."""
    diagnostic = None
    try:
        if error.code == 400:
            raw = error.read(8193)
            if isinstance(raw, bytes) and len(raw) <= 8192:
                def invalid_constant(_value):
                    raise ValueError('non-JSON constant')
                payload = json.loads(raw.decode('utf-8'), parse_constant=invalid_constant)
                detail = payload.get('error') if isinstance(payload, dict) else None
                message = detail.get('message') if isinstance(detail, dict) else None
                if isinstance(message, str):
                    text = message.casefold()
                    if (re.search(r'\bmessages\b\W+must\s+contain\s+(?:the\s+)?word\W+json\b', text)
                            and re.search(r'\bresponse_format\b', text)
                            and re.search(r'\bjson_object\b', text)):
                        diagnostic = 'json_instruction_missing'
    except (OSError, http.client.HTTPException, ValueError, TypeError, RecursionError):
        pass  # A failed diagnostic read cannot change the known HTTP status.
    finally:
        try:
            error.close()
        except (OSError, http.client.HTTPException, ValueError):
            pass
    return diagnostic


class BudgetExceeded(RuntimeError):
    pass


# Keep the existing process-wide thread admission guard as well as the
# resource-specific kernel lock used below for independent app processes.
_LEDGER_LOCK = threading.Lock()


def _reset_admission_lock_after_fork():
    global _LEDGER_LOCK
    _LEDGER_LOCK = threading.Lock()


platform_compat.after_fork_in_child(_reset_admission_lock_after_fork)


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
        with target.open("w", encoding="utf-8") as handle:
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
        """Effective aggregate policy; None means no limit, never a zero balance."""
        policy = dict(self.config["policy"])
        policy.setdefault('aggregate_limits_enabled', True)
        if self.dev:
            policy.update(DEV_POLICY)
        if not policy['aggregate_limits_enabled']:
            for field in ('daily_background_tokens', 'daily_interactive_tokens',
                          'daily_total_tokens', 'monthly_total_tokens', 'daily_usd', 'monthly_usd'):
                policy[field] = None
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
            marker.write_text("AI disabled by owner\n", encoding="utf-8")
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
            for line in self.ledger.read_text(encoding="utf-8").splitlines():
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
            self.check_aggregate(day, month, cap_in + cap_out, reserve_usd)
            return cap_in, cap_out, reserve_usd

    def check_aggregate(self, day, month, tokens, usd):
        """Raise BudgetExceeded when explicitly enabled day/month ceilings cannot hold `tokens`/`usd`."""
        policy = self.limits()
        if not policy['aggregate_limits_enabled']:
            return
        (day_tokens, day_usd), (month_tokens, month_usd) = self._usage(day, month)
        if day_tokens + tokens > policy["daily_total_tokens"]:
            raise BudgetExceeded(f"daily token ceiling ({day_tokens:,}/{policy['daily_total_tokens']:,} used)")
        if month_tokens + tokens > policy["monthly_total_tokens"]:
            raise BudgetExceeded(f"monthly token ceiling ({month_tokens:,}/{policy['monthly_total_tokens']:,} used)")
        if day_usd + usd > Decimal(str(policy["daily_usd"])):
            raise BudgetExceeded(f"daily USD ceiling (${day_usd:.4f}/${policy['daily_usd']} used)")
        if month_usd + usd > Decimal(str(policy["monthly_usd"])):
            raise BudgetExceeded(f"monthly USD ceiling (${month_usd:.4f}/${policy['monthly_usd']} used)")

    def usage_today(self):
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        with self._ledger_serial():
            (tokens, usd), (month_tokens, month_usd) = self._usage(today, today[:7])
            pending = [row for row in self._entries() if row.get('status') in ('reserved', 'unknown')]
            day_pending = [row for row in pending if row['date'] == today]
            month_pending = [row for row in pending if row['date'].startswith(today[:7])]
            reserved = lambda rows: (sum(int(row.get('input', 0)) + int(row.get('output', 0)) for row in rows),
                                     sum((Decimal(str(row.get('usd', '0'))) for row in rows), Decimal(0)))
            reserved_tokens, reserved_usd = reserved(day_pending)
            month_reserved_tokens, month_reserved_usd = reserved(month_pending)
        policy = self.limits()
        return {"tokens": tokens, "usd": str(usd), "month_tokens": month_tokens, "month_usd": str(month_usd),
                "ceiling": policy["daily_total_tokens"], "aggregate_limits_enabled": policy['aggregate_limits_enabled'],
                "tokens_known": not day_pending, "month_tokens_known": not month_pending,
                "pending_reservations": len(day_pending), "month_pending_reservations": len(month_pending),
                "reserved_tokens": reserved_tokens, "reserved_usd": str(reserved_usd),
                "month_reserved_tokens": month_reserved_tokens, "month_reserved_usd": str(month_reserved_usd),
                "dev": self.dev, "enabled": self.enabled()}

    def _append(self, entry):
        with self._ledger_serial():
            self.ledger.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger.open("a", encoding="utf-8") as handle:
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
    def test_connection(self, test_key=None, dry_run=False, timeout=30):
        """One explicit fixed request, even when AI is off; never persists its key."""
        result = self.call(CONNECTION_TEST_OPERATION,
                           [{'role': 'user', 'content': CONNECTION_TEST_MESSAGE}],
                           dry_run=dry_run, timeout=timeout, connection_test_key=test_key)
        # A connection check needs no provider prose, which is untrusted data.
        return {key: value for key, value in result.items() if key != 'content'}

    def call(self, operation, messages, dry_run=False, timeout=90, *, connection_test_key=None):
        # The explicit test also turns pre-send lock/read failures into a local
        # diagnostic. Keep a per-call phase so an unexpected post-send I/O
        # failure cannot be reported as unpaid; regular operations still raise.
        state = {} if operation == CONNECTION_TEST_OPERATION else None
        try:
            return self._call(operation, messages, dry_run=dry_run, timeout=timeout,
                              connection_test_key=connection_test_key, _connection_state=state)
        except OSError:
            if state is None:
                raise
            return _connection_tracking_failure(state.get('reservation') if state.get('sent') else None)

    def _call(self, operation, messages, dry_run=False, timeout=90, *,
              connection_test_key=None, _connection_state=None):
        """Call the runtime provider for a registered operation. Returns dict or None.

        One attempt only: no retry, no model fallback. The envelope is written to
        the ledger as an in-flight reservation before sending and is reconciled
        only when the provider reports usage.
        """
        import datetime
        import uuid
        connection_test = operation == CONNECTION_TEST_OPERATION
        invalid_test_key = (connection_test_key is not None and (
            not isinstance(connection_test_key, str) or not connection_test_key.strip()
            or len(connection_test_key.strip()) > 512
            or any(not 33 <= ord(char) <= 126 for char in connection_test_key.strip())))
        if ((connection_test_key is not None and not connection_test) or invalid_test_key
                or (connection_test and messages != [{'role': 'user', 'content': CONNECTION_TEST_MESSAGE}])):
            return {'ok': False, 'degraded': True, 'invalid_input': True, 'usage_unknown': False,
                    'reason': 'invalid connection test input; nothing sent'}
        if not self.enabled() and not connection_test:
            return {"ok": False, "degraded": True, "disabled": True, "reason": "AI 已关闭"}
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        month = today[:7]
        provider = self.config["provider"]
        with _LEDGER_LOCK, self._ledger_serial():
            try:
                cap_in, cap_out, reserve_usd = self.admit(operation, today, month)
            except BudgetExceeded as exc:
                return {"ok": False, "degraded": True, "reason": str(exc)}
            # The operation's cap is an estimate (owner 2026-10-22), never a reason to refuse or cut. Only the
            # model's own window bounds a request; conversations ask for its longest answer, other operations
            # keep cap.output as a guard against a runaway reply.
            window = provider.get('context_tokens')
            wanted = (provider.get('max_output_tokens') or cap_out
                      if self.config["operations"][operation].get('conversation') else cap_out)
            try:
                envelope = request_envelope(operation, provider["model"], wanted, messages)
                bound = input_bound(envelope)
                if window and bound + min(wanted, cap_out) > window:
                    return {"ok": False, "degraded": True, "invalid_input": True, "input_too_large": True,
                            "usage_unknown": False, "input_bound": bound, "context_tokens": window,
                            "reason": "这次的问题、资料和历史超过了模型一次能读的最大长度；请开始新会话或缩短选区。未发送请求。"}
                if window and bound + wanted > window:   # a very long conversation leaves less room to answer
                    wanted = window - bound
                    envelope = request_envelope(operation, provider["model"], wanted, messages)
                    bound = input_bound(envelope)
                body = json.dumps(envelope, ensure_ascii=False, allow_nan=False).encode('utf-8')
                if any(isinstance(m.get('content'), list) for m in messages) and operation != 'paper_vision_qa':
                    raise ValueError('images outside reader vision operation')
            except (UnicodeError, TypeError, ValueError, RecursionError):
                return {"ok": False, "degraded": True, "invalid_input": True,
                        "usage_unknown": False, "reason": "invalid request text; nothing sent"}
            # Hold at least what this request can actually cost until the provider reports usage.
            cap_in, cap_out = max(cap_in, bound), wanted
            reserve_usd = _cost(provider, cap_in, cap_out)
            try:   # explicitly enabled ceilings (developer policy) judge what is really held, not the estimate
                self.check_aggregate(today, month, cap_in + cap_out, reserve_usd)
            except BudgetExceeded as exc:
                return {"ok": False, "degraded": True, "reason": str(exc)}
            if dry_run:
                return {"ok": True, "dry_run": True, "operation": operation,
                        "input_bound": bound,
                        "reservation": {"input": cap_in, "output": cap_out, "usd": str(reserve_usd)}}
            key, _source = ((connection_test_key.strip(), 'temporary connection test')
                            if connection_test_key is not None else self._load_key())
            if not key:
                return {"ok": False, "degraded": True, "reason": "no API key"}
            if connection_test and (not isinstance(key, str) or len(key) > 512
                    or any(not 33 <= ord(char) <= 126 for char in key)):
                return {'ok': False, 'degraded': True, 'invalid_input': True, 'usage_unknown': False,
                        'reason': 'invalid connection test key; nothing sent'}
            rid = uuid.uuid4().hex
            try:
                self._record(today, operation, {"prompt_tokens": cap_in, "completion_tokens": cap_out},
                             reserve_usd, provider["model"], rid, "reserved")
            except OSError:
                if connection_test:
                    return _connection_tracking_failure()
                raise
        request = urllib.request.Request(
            DEEPSEEK_URL, data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                     "User-Agent": "PaperDigHelper/0.1 (local app)"})
        reservation = {"input": cap_in, "output": cap_out, "usd": str(reserve_usd)}
        if _connection_state is not None:
            _connection_state.update(sent=True, reservation=reservation)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            provider_error = _http_provider_error(exc)
            if 400 <= exc.code < 500:
                # Rejected before generation (auth, balance, validation, rate limit).
                try:
                    self._record(today, operation, {}, Decimal(0), provider["model"], rid, "released")
                except OSError:
                    if connection_test:
                        result = _connection_tracking_failure(reservation, exc.code)
                        if provider_error:
                            result['provider_error'] = provider_error
                        return result
                    raise
            result = {"ok": False, "degraded": True, "usage_unknown": not 400 <= exc.code < 500,
                      "usage_reserved": not 400 <= exc.code < 500,
                      "reservation": reservation if not 400 <= exc.code < 500 else None,
                      "http_status": exc.code, "reason": f"HTTPError: {exc.code}"}
            if provider_error:
                result['provider_error'] = provider_error
            return result
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            # The request may have been processed: keep the reservation charged.
            return {"ok": False, "degraded": True, "usage_unknown": True,
                    "usage_reserved": True, "reservation": reservation,
                    "reason": type(exc).__name__ if connection_test else f"{type(exc).__name__}: {exc}"}
        usage = payload.get("usage") if isinstance(payload, dict) else None
        model = provider['model'] if connection_test else (payload.get("model") if isinstance(payload, dict) else None) or provider["model"]
        choices = payload.get('choices') if isinstance(payload, dict) else None
        choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        message = choice.get('message')
        content = message.get('content') if isinstance(message, dict) else None
        finish_reason = choice.get('finish_reason')
        valid_content = isinstance(content, str) and bool(content.strip()) and finish_reason != 'length'
        if valid_content:
            try:
                content.encode('utf-8')
            except UnicodeError:
                valid_content = False
        valid_usage = (isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0
                      for k in ('prompt_tokens', 'completion_tokens'))
                      and type(usage.get('prompt_cache_hit_tokens', 0)) is int
                      and 0 <= usage.get('prompt_cache_hit_tokens', 0) <= usage.get('prompt_tokens', 0))
        if not valid_usage:
            try:
                self._record(today, operation, {"prompt_tokens": cap_in, "completion_tokens": cap_out},
                             reserve_usd, model, rid, "unknown")
            except OSError:
                if connection_test:
                    return _connection_tracking_failure(reservation)
                raise
            if not valid_content:
                return {"ok": False, "degraded": True, "bad_reply": True,
                        "reason": "AI 回复须为非空完整文本；未保存回复", "finish_reason": finish_reason,
                        "usage": {"total_tokens": cap_in + cap_out},
                        "usage_unknown": True, "usage_reserved": True, "reservation": reservation,
                        "usd": str(reserve_usd), "model": model, "dev": self.dev}
            return {"ok": True, "content": content, 'finish_reason': finish_reason, "usage": {"total_tokens": cap_in + cap_out},
                    "usage_unknown": True, "usage_reserved": True, "reservation": reservation,
                    "usd": str(reserve_usd), "model": model, "dev": self.dev}
        usd = _cost(provider, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                    usage.get("prompt_cache_hit_tokens", 0))
        try:
            self._record(today, operation, usage, usd, model, rid, "reconciled")
        except OSError:
            if connection_test:
                return _connection_tracking_failure(reservation)
            raise
        if not valid_content:
            return {"ok": False, "degraded": True, "bad_reply": True,
                    "reason": "AI 回复须为非空完整文本；未保存回复", "finish_reason": finish_reason, "usage": usage,
                    "usd": str(usd), "model": model, "usage_unknown": False, "usage_reserved": False}
        return {"ok": True, "content": content, 'finish_reason': finish_reason, "usage": usage, "usd": str(usd),
                "model": model, "dev": self.dev, "usage_unknown": False, "usage_reserved": False}

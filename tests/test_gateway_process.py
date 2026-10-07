"""Kernel ledger admission regressions with isolated data and synthetic providers."""
import datetime
import json
import io
import multiprocessing
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.gateway import Gateway


def _race_gateway(data, paused, release, sent, results, first):
    gateway = Gateway(root=ROOT, data_dir=data, dev=False)
    usage = gateway._usage
    if first:
        def snapshot_then_pause(day, month):
            snapshot = usage(day, month)
            paused.set()
            if not release.wait(10):
                raise RuntimeError('fixture admission pause timed out')
            return snapshot
        gateway._usage = snapshot_then_pause
    def provider(request, timeout):
        sent.set()
        raise TimeoutError('synthetic unknown provider outcome')
    try:
        with mock.patch.object(gateway, '_load_key', return_value=('synthetic-key', 'fixture')), \
                mock.patch('app.gateway.urllib.request.urlopen', side_effect=provider):
            result = gateway.call('route_growth_judge', [])
        results.put(result)
    except BaseException as exc:
        results.put({'fixture_error': f'{type(exc).__name__}: {exc}'})


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _network_gateway(data, sent, release, results, hold):
    gateway = Gateway(root=ROOT, data_dir=data, dev=False)
    def provider(request, timeout):
        sent.set()
        if hold:
            if not release.wait(10):
                raise RuntimeError('fixture provider pause timed out')
            raise TimeoutError('synthetic unknown outcome')
        return _Response(json.dumps({'choices': [{'message': {'content': 'fixture'}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}}).encode())
    try:
        with mock.patch.object(gateway, '_load_key', return_value=('synthetic-key', 'fixture')), \
                mock.patch('app.gateway.urllib.request.urlopen', side_effect=provider):
            results.put(gateway.call('route_growth_judge', []))
    except BaseException as exc:
        results.put({'fixture_error': f'{type(exc).__name__}: {exc}'})


def _partial_append(data, partial, release, results):
    gateway = Gateway(root=ROOT, data_dir=data, dev=False)
    original = Path.open
    class PausedWrite:
        def __init__(self, handle):
            self.handle = handle
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return self.handle.__exit__(*exc)
        def write(self, text):
            split = len(text) // 2
            self.handle.write(text[:split])
            self.handle.flush()
            partial.set()
            if not release.wait(10):
                raise RuntimeError('fixture partial write pause timed out')
            return self.handle.write(text[split:])
    def opening(path, *args, **kwargs):
        handle = original(path, *args, **kwargs)
        return PausedWrite(handle) if path == gateway.ledger and args == ('a',) else handle
    try:
        with mock.patch.object(Path, 'open', opening):
            gateway._append({'date': '2026-10-07', 'operation': 'fixture', 'id': 'r1',
                'input': 100, 'output': 20, 'usd': '0', 'status': 'reconciled'})
        results.put({'writer': 'done'})
    except BaseException as exc:
        results.put({'fixture_error': f'{type(exc).__name__}: {exc}'})


def _read_entries(data, started, finished, results):
    gateway = Gateway(root=ROOT, data_dir=data, dev=False)
    started.set()
    try:
        results.put({'entries': gateway._entries()})
    except BaseException as exc:
        results.put({'fixture_error': f'{type(exc).__name__}: {exc}'})
    finally:
        finished.set()


class GatewayProcessTests(unittest.TestCase):
    def test_two_processes_cannot_both_reserve_the_last_envelope(self):
        context = multiprocessing.get_context('spawn')
        with tempfile.TemporaryDirectory() as data:
            gateway = Gateway(root=ROOT, data_dir=data, dev=False)
            today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
            gateway._append({'date': today, 'operation': 'fixture', 'input': 45000,
                             'output': 0, 'usd': '0'})
            paused, release = context.Event(), context.Event()
            first_sent, second_sent = context.Event(), context.Event()
            results = context.Queue()
            first = context.Process(target=_race_gateway,
                args=(data, paused, release, first_sent, results, True))
            alias = Path(data) / 'same-data'
            alias.symlink_to(data, target_is_directory=True)
            second = context.Process(target=_race_gateway,
                args=(str(alias), paused, release, second_sent, results, False))
            first.start()
            try:
                self.assertTrue(paused.wait(10), 'first process did not take its usage snapshot')
                second.start()
                # The old implementation admits process two during process one's
                # pre-reservation gap. The fixed implementation waits on the kernel lock.
                second_sent.wait(1)
                release.set()
                first.join(10)
                second.join(10)
                self.assertFalse(first.is_alive())
                self.assertFalse(second.is_alive())
                self.assertEqual((first.exitcode, second.exitcode), (0, 0))
                replies = [results.get(timeout=3) for _ in range(2)]
                self.assertFalse(any('fixture_error' in r for r in replies), replies)
                self.assertEqual((sum((first_sent.is_set(), second_sent.is_set())),
                                  gateway.usage_today()['tokens']), (1, 54000))
                refused = [r for r in replies if not r.get('usage_unknown')]
                self.assertEqual(len(refused), 1)
                self.assertIn('daily token ceiling', refused[0]['reason'])
            finally:
                release.set()
                for process in (first, second):
                    if process.pid is not None:
                        if process.is_alive():
                            process.terminate()
                        process.join(3)
                results.close()
                results.join_thread()


    def test_another_process_can_reconcile_while_the_first_waits_on_network(self):
        context = multiprocessing.get_context('spawn')
        with tempfile.TemporaryDirectory() as data:
            release = context.Event()
            first_sent, second_sent = context.Event(), context.Event()
            results = context.Queue()
            first = context.Process(target=_network_gateway,
                args=(data, first_sent, release, results, True))
            second = context.Process(target=_network_gateway,
                args=(data, second_sent, release, results, False))
            first.start()
            try:
                self.assertTrue(first_sent.wait(10))
                second.start()
                self.assertTrue(second_sent.wait(5), 'ledger lock was held during the provider request')
                second.join(5)
                self.assertFalse(second.is_alive(), 'reconciliation blocked on another network request')
                release.set()
                first.join(10)
                replies = [results.get(timeout=3) for _ in range(2)]
                self.assertEqual((first.exitcode, second.exitcode), (0, 0))
                self.assertFalse(any('fixture_error' in r for r in replies), replies)
                self.assertEqual(sum(bool(r.get('usage_unknown')) for r in replies), 1)
                self.assertEqual(Gateway(root=ROOT, data_dir=data, dev=False).usage_today()['tokens'], 9120)
            finally:
                release.set()
                for process in (first, second):
                    if process.pid is not None:
                        if process.is_alive():
                            process.terminate()
                        process.join(3)
                results.close()
                results.join_thread()

    def test_entries_wait_for_a_complete_cross_process_append(self):
        context = multiprocessing.get_context('spawn')
        with tempfile.TemporaryDirectory() as data:
            partial, release = context.Event(), context.Event()
            started, finished = context.Event(), context.Event()
            results = context.Queue()
            writer = context.Process(target=_partial_append, args=(data, partial, release, results))
            reader = context.Process(target=_read_entries, args=(data, started, finished, results))
            writer.start()
            try:
                self.assertTrue(partial.wait(10))
                reader.start()
                self.assertTrue(started.wait(10))
                read_partial_row = finished.wait(.5)
                release.set()
                writer.join(10)
                reader.join(10)
                self.assertEqual((writer.exitcode, reader.exitcode), (0, 0))
                replies = [results.get(timeout=3) for _ in range(2)]
                self.assertFalse(read_partial_row, 'reader bypassed an in-progress append')
                self.assertFalse(any('fixture_error' in r for r in replies), replies)
                entries = next(r['entries'] for r in replies if 'entries' in r)
                self.assertEqual(len(entries), 1)
                self.assertEqual((entries[0]['id'], entries[0]['status']), ('r1', 'reconciled'))
            finally:
                release.set()
                for process in (writer, reader):
                    if process.pid is not None:
                        if process.is_alive():
                            process.terminate()
                        process.join(3)
                results.close()
                results.join_thread()

    def test_nested_serial_sections_share_one_lock_across_gateway_instances(self):
        with tempfile.TemporaryDirectory() as data:
            first = Gateway(root=ROOT, data_dir=data, dev=False)
            alias = Path(data) / 'alias'
            alias.symlink_to(data, target_is_directory=True)
            second = Gateway(root=ROOT, data_dir=alias, dev=False)
            done, errors = threading.Event(), []
            def nested():
                try:
                    with first._ledger_serial(), second._ledger_serial():
                        second._append({'date': '2026-10-07', 'input': 1, 'output': 0, 'usd': '0'})
                        self.assertEqual(len(first._entries()), 1)
                        self.assertEqual(second._usage('2026-10-07', '2026-10')[0][0], 1)
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    done.set()
            worker = threading.Thread(target=nested, daemon=True)
            worker.start()
            self.assertTrue(done.wait(3), 'nested same-resource flock deadlocked')
            worker.join(1)
            self.assertEqual(errors, [])

    def test_serial_thread_waiter_gets_the_lock_after_an_exception(self):
        with tempfile.TemporaryDirectory() as data:
            first = Gateway(root=ROOT, data_dir=data, dev=False)
            second = Gateway(root=ROOT, data_dir=data, dev=False)
            started, entered, finished = threading.Event(), threading.Event(), threading.Event()
            def waiter():
                started.set()
                with second._ledger_serial():
                    entered.set()
                finished.set()
            worker = threading.Thread(target=waiter, daemon=True)
            with self.assertRaisesRegex(ValueError, 'synthetic'):
                with first._ledger_serial():
                    worker.start()
                    self.assertTrue(started.wait(3))
                    self.assertFalse(entered.wait(.2))
                    raise ValueError('synthetic release test')
            self.assertTrue(finished.wait(3))
            worker.join(1)

    def test_real_gateway_thread_calls_share_the_last_reservation(self):
        with tempfile.TemporaryDirectory() as data:
            first = Gateway(root=ROOT, data_dir=data, dev=False)
            second = Gateway(root=ROOT, data_dir=data, dev=False)
            today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
            first._append({'date': today, 'input': 45000, 'output': 0, 'usd': '0'})
            sent, release, second_done = threading.Event(), threading.Event(), threading.Event()
            calls, replies, errors = [], [], []
            def provider(request, timeout):
                calls.append(request)
                sent.set()
                if not release.wait(5):
                    raise RuntimeError('fixture provider release timed out')
                raise TimeoutError('synthetic unknown outcome')
            def run(gateway, finished=None):
                try:
                    replies.append(gateway.call('route_growth_judge', []))
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    if finished is not None:
                        finished.set()
            one = threading.Thread(target=run, args=(first,), daemon=True)
            two = threading.Thread(target=run, args=(second, second_done), daemon=True)
            with mock.patch.object(Gateway, '_load_key', return_value=('synthetic-key', 'fixture')), \
                    mock.patch('app.gateway.urllib.request.urlopen', side_effect=provider):
                one.start()
                try:
                    self.assertTrue(sent.wait(3))
                    two.start()
                    self.assertTrue(second_done.wait(3), 'admission guard remained held during network')
                finally:
                    release.set()
                    one.join(3)
                    if two.ident is not None:
                        two.join(3)
            self.assertFalse(one.is_alive())
            self.assertFalse(two.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(calls), 1)
            self.assertEqual(first.usage_today()['tokens'], 54000)
            self.assertEqual(sum(bool(r.get('usage_unknown')) for r in replies), 1)
            self.assertTrue(any('daily token ceiling' in r.get('reason', '') for r in replies))

    @unittest.skipUnless('fork' in multiprocessing.get_all_start_methods(), 'fork unavailable')
    def test_forked_gateway_resets_the_process_local_admission_mutex(self):
        from app.gateway import _LEDGER_LOCK
        context = multiprocessing.get_context('fork')
        with tempfile.TemporaryDirectory() as data:
            sent, release = context.Event(), context.Event()
            results = context.Queue()
            child = context.Process(target=_network_gateway, args=(data, sent, release, results, False))
            try:
                with _LEDGER_LOCK:
                    child.start()
                    self.assertTrue(sent.wait(5), 'child inherited a locked process-local admission mutex')
                    child.join(5)
                    self.assertEqual(child.exitcode, 0)
                self.assertTrue(results.get(timeout=3)['ok'])
            finally:
                if child.pid is not None:
                    if child.is_alive():
                        child.terminate()
                    child.join(3)
                results.close()
                results.join_thread()

    @unittest.skipUnless('fork' in multiprocessing.get_all_start_methods(), 'fork unavailable')
    def test_forked_child_does_not_inherit_a_reentrant_admission(self):
        context = multiprocessing.get_context('fork')
        with tempfile.TemporaryDirectory() as data:
            gateway = Gateway(root=ROOT, data_dir=data, dev=False)
            started, finished = context.Event(), context.Event()
            results = context.Queue()
            child = context.Process(target=_read_entries, args=(data, started, finished, results))
            try:
                with gateway._ledger_serial():
                    child.start()
                    self.assertTrue(started.wait(5))
                    bypassed = finished.wait(.2)
                child.join(5)
                self.assertEqual(child.exitcode, 0)
                self.assertFalse(bypassed, 'child inherited parent reentrancy and bypassed flock')
                self.assertEqual(results.get(timeout=3), {'entries': []})
            finally:
                if child.pid is not None:
                    if child.is_alive():
                        child.terminate()
                    child.join(3)
                results.close()
                results.join_thread()


if __name__ == '__main__':
    unittest.main()

"""Pipe helpers that work on Windows (select.select cannot wait on a pipe there)."""
import queue
import threading


def read_line(stream, timeout):
    """One line from a pipe within `timeout` seconds, or None."""
    lines = queue.Queue()
    threading.Thread(target=lambda: lines.put(stream.readline()), daemon=True).start()
    try:
        return lines.get(timeout=timeout)
    except queue.Empty:
        return None

"""Every text-mode file/pipe in app/ and scripts/ names its encoding.

The PyInstaller-frozen Windows exe ignored PYTHONUTF8 and read UTF-8 files with the cp1252 code page
(UnicodeDecodeError in load_budget). macOS never shows this, so guard it statically.
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUBPROCESS = {"run", "Popen", "check_output", "check_call", "call"}
TEMP = {"NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile"}


def _const(node):
    return node.value if isinstance(node, ast.Constant) else None


def offences(source, name="<test>"):
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        attr = func.attr if isinstance(func, ast.Attribute) else None
        ident = func.id if isinstance(func, ast.Name) else None
        receiver = func.value.id if attr and isinstance(func.value, ast.Name) else None
        keywords = {k.arg: k.value for k in node.keywords}
        args = node.args
        has_encoding = "encoding" in keywords
        label = f"{name}:{node.lineno}"
        if attr in ("read_text", "write_text"):
            if not has_encoding and len(args) < (1 if attr == "read_text" else 2):
                found.append(f"{label} {attr} without encoding")
        elif (receiver, attr) in (("os", "popen"), ("subprocess", "getoutput"), ("subprocess", "getstatusoutput")):
            found.append(f"{label} {receiver}.{attr} decodes with the locale code page")
        elif ident == "open" or (receiver in ("io", "codecs", "builtins") and attr == "open") or (receiver == "os" and attr == "fdopen"):
            # open(file, mode, buffering, encoding) / io.open / os.fdopen(fd, mode): mode is the second argument.
            # codecs.open(file, mode, encoding): the encoding is the third.
            encoding_position = 2 if receiver == "codecs" else 3
            mode_node = args[1] if len(args) > 1 else keywords.get("mode")
            mode = _const(mode_node) if mode_node is not None else "r"
            if (mode is None or "b" not in mode) and not has_encoding and len(args) <= encoding_position:
                found.append(f"{label} text-mode open without encoding")
        elif attr == "open" and receiver != "os":
            # Path.open(mode): mode is the first argument. opener.open(url) takes a non-constant first argument.
            if args and not isinstance(_const(args[0]), str):
                continue
            mode_node = args[0] if args else keywords.get("mode")
            mode = _const(mode_node) if mode_node is not None else "r"
            if (mode is None or "b" not in mode) and not has_encoding and len(args) < 4:
                found.append(f"{label} text-mode open without encoding")
        elif (ident in TEMP or attr in TEMP) and ("mode" in keywords or args):
            mode_node = keywords.get("mode", args[0] if args else None)
            mode = _const(mode_node)
            if (mode is None or "b" not in mode) and not has_encoding:
                found.append(f"{label} text-mode temporary file without encoding")
        elif (ident in SUBPROCESS or attr in SUBPROCESS) and any(
                k in keywords and _const(keywords[k]) is not False for k in ("text", "universal_newlines")) and not has_encoding:
            found.append(f"{label} subprocess text mode without encoding")
    return found


class TextEncodingTests(unittest.TestCase):
    def test_detector_recognises_the_patterns(self):
        bad = ["open('x')", "open('x', 'w')", "p.read_text()", "p.write_text('a')", "p.open('a')", "p.open()",
               "os.fdopen(fd, 'w')", "subprocess.run(c, text=True)", "subprocess.Popen(c, universal_newlines=True)",
               "tempfile.NamedTemporaryFile(mode='w')", "tempfile.NamedTemporaryFile('w')", "io.open(path)",
               "io.open(path, 'w')", "codecs.open(path, 'r')", "open(path, mode)", "open(path, 'r', -1)",
               "os.popen('x')", "subprocess.getoutput('x')"]
        for source in bad:
            self.assertTrue(offences(source), source)
        good = ["open('x', 'rb')", "open('x', encoding='utf-8')", "p.read_text(encoding='utf-8')", "p.open('ab')",
                "p.open('a', encoding='utf-8')", "os.open(p, 0)", "opener.open(request, timeout=5)",
                "os.fdopen(fd, 'wb')", "subprocess.run(c)", "subprocess.run(c, text=True, encoding='utf-8')",
                "tempfile.NamedTemporaryFile(mode='wb')", "tempfile.mkstemp()", "io.open(path, 'rb')", "codecs.open(path, 'r', 'utf-8')",
                "open(path, 'r', -1, 'utf-8')", "p.read_text('utf-8')", "p.write_text('a', 'utf-8')"]
        for source in good:
            self.assertEqual(offences(source), [], source)

    def test_no_implicit_locale_encoding_in_app_and_scripts(self):
        found = []
        for base in ("app", "scripts"):
            for path in sorted((ROOT / base).rglob("*.py")):
                if "static" in path.parts:
                    continue
                found += offences(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))
        self.assertEqual(found, [])


class StreamTests(unittest.TestCase):
    def test_std_streams_are_forced_to_utf8_even_under_a_legacy_code_page(self):
        import os
        import subprocess
        import sys
        env = dict(os.environ, PYTHONUTF8="0", PYTHONIOENCODING="cp1252")
        code = ("import sys; from app import platform_compat as p; p.force_utf8_std_streams(); "
                "data = sys.stdin.buffer.raw.read() if False else sys.stdin.read(); print(data + '中文')")
        done = subprocess.run([sys.executable, "-c", code], input="é".encode("utf-8"), stdout=subprocess.PIPE,
                              cwd=ROOT, env=env, check=True)
        self.assertEqual(done.stdout.decode("utf-8").strip(), "é中文")


if __name__ == "__main__":
    unittest.main()

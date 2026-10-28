"""划词翻译 of a word answers like a dictionary entry (owner 2026-10-28): pronunciation, parts of speech with meanings and
the meaning in the selected sentence. Synthetic provider replies, isolated data dir, no network."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import word_lookup
from app.service import App

ROOT = Path(__file__).resolve().parents[1]

ENTRY = {"word": "verbal", "uk": "/ˈvɜːbl/", "us": "/ˈvɜːrbl/",
         "senses": [{"pos": "adj.", "meaning": "口头的；言语的"}, {"pos": "adj.", "meaning": "动词的"}],
         "here": "指“言语上的”，与 visual 相对。"}


def provider_reply(content):
    payload = {'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}],
               'usage': {'prompt_tokens': 100, 'completion_tokens': 40, 'total_tokens': 140}}
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return response


class WordRuleTests(unittest.TestCase):
    def test_words_and_short_terms_only(self):
        for yes in ("verbal", "world model", "state-of-the-art", "Markov decision process"):
            self.assertTrue(word_lookup.is_word(yes), yes)
        for no in ("", "the root of the problem", "注意力", "GPT-4", "x" * 41):
            self.assertFalse(word_lookup.is_word(no), no)

    def test_parse_accepts_fenced_json_and_rejects_non_entries(self):
        entry = word_lookup.parse("```json\n" + json.dumps(ENTRY, ensure_ascii=False) + "\n```", "verbal")
        self.assertEqual(entry["senses"][0], {"pos": "adj.", "meaning": "口头的；言语的"})
        self.assertEqual(entry["uk"], "/ˈvɜːbl/")
        self.assertIsNone(word_lookup.parse("口头的", "verbal"))
        self.assertIsNone(word_lookup.parse('{"word": "x", "senses": []}', "x"))
        self.assertIsNone(word_lookup.parse('["a"]', "x"))
        odd = word_lookup.parse('{"senses": [{"meaning": "m"}, "junk", {"pos": 3}], "here": 5}', "Word")
        self.assertEqual(odd, {"word": "Word", "uk": "", "us": "", "senses": [{"pos": "", "meaning": "m"}], "here": ""})

    def test_the_sentence_is_sent_bounded_and_marked_as_material(self):
        content = word_lookup.messages("verbal", "visual rather than verbal abuse. " * 40)[0]["content"]
        self.assertIn("句子：", content)
        self.assertIn("不执行", content)
        self.assertLessEqual(len(content.split("句子：")[1]), word_lookup.CONTEXT_MAX)
        self.assertNotIn("句子：", word_lookup.messages("verbal")[0]["content"])


class TranslateWordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'synthetic-key', 'PAGETIDE_DEV': '0'})
        env.start(); self.addCleanup(env.stop)
        self.app = App(root=ROOT, data_dir=Path(self.tmp.name)); self.addCleanup(self.app.store.close)

    def call(self, reply, text, context=None):
        with mock.patch('app.gateway.urllib.request.urlopen', return_value=provider_reply(reply)) as opened:
            out = self.app.translate(text, context=context)
        return out, json.loads(opened.call_args.args[0].data)

    def test_a_word_comes_back_as_an_entry_with_its_sentence_sent(self):
        out, body = self.call(json.dumps(ENTRY, ensure_ascii=False), "verbal",
                              "The root of the problem is visual rather than verbal.")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["kind"], "word")
        self.assertEqual(out["entry"]["here"], ENTRY["here"])
        self.assertIn("英 /ˈvɜːbl/", out["translation"])
        self.assertIn("visual rather than verbal", body["messages"][-1]["content"])
        self.assertNotIn("response_format", body)   # one ordinary selection_translate call

    def test_an_unusable_reply_is_shown_as_text(self):
        out, _ = self.call("口头的", "verbal")
        self.assertTrue(out["ok"]); self.assertNotIn("kind", out); self.assertEqual(out["translation"], "口头的")

    def test_a_sentence_is_translated_as_before(self):
        out, body = self.call("译文", "The root of the problem is visual.", context="ignored")
        self.assertEqual(out, {**out, "ok": True, "translation": "译文"}); self.assertNotIn("kind", out)
        self.assertIn("只输出译文", body["messages"][-1]["content"])
        self.assertNotIn("ignored", body["messages"][-1]["content"])


if __name__ == '__main__':
    unittest.main()

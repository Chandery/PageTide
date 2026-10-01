"""CHAN-01: Chinese tokens and titles, without changing English behaviour."""
import json
import random
import re
import unittest
from pathlib import Path

from app import ranking, sources
from app.channels import text as chtext

ROOT = Path(__file__).resolve().parents[1]


def old_tokenize(text):
    words = re.findall(r"[a-z0-9][a-z0-9\-]+", (text or "").lower())
    return [w for w in words if len(w) >= 3 and w not in ranking.STOPWORDS]


def old_normalize_title(text):
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def english_corpus():
    seeds = json.loads((ROOT / "harness" / "seeds.json").read_text())["seeds"]
    docs = [s.get("title") or "" for s in seeds]
    docs += [
        "DINO-WM: World Models on Pre-trained Visual Features enable Zero-shot Planning",
        "V-JEPA 2: Self-Supervised Video Models Enable Understanding, Prediction and Planning",
        "Ångström-scale café naïve résumé — über Straße (ﬁne) “quoted” 3–5 × 10⁻³",
        "étude décomposée; tab\tnew\nline   spaces",
        "", "   ", "a-b--c x-ray state-of-the-art GPT-4o 2025 1e-3",
    ]
    rng = random.Random(20261001)
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_.,:;!?()[]'\"/\\\t\néüßøñ"
    for _ in range(400):
        docs.append("".join(rng.choice(alphabet) for _ in range(rng.randint(0, 120))))
    return docs


class EnglishUnchanged(unittest.TestCase):
    def test_tokenize_matches_previous_tokenizer_byte_for_byte(self):
        for doc in english_corpus():
            self.assertEqual(ranking.tokenize(doc), old_tokenize(doc), repr(doc))

    def test_normalize_title_matches_previous_for_text_without_cjk_or_fullwidth(self):
        for doc in english_corpus():
            self.assertEqual(sources.normalize_title(doc), old_normalize_title(doc), repr(doc))

    def test_none_is_handled(self):
        self.assertEqual(ranking.tokenize(None), [])
        self.assertEqual(sources.normalize_title(None), "")


class ChineseTokens(unittest.TestCase):
    def test_han_runs_become_bigrams(self):
        self.assertEqual(ranking.tokenize("数字人文"), ["数字", "字人", "人文"])

    def test_mixed_text_keeps_english_tokens_first(self):
        tokens = ranking.tokenize("基于Transformer的古籍命名实体识别")
        self.assertEqual(tokens[0], "transformer")
        for bigram in ("古籍", "命名", "实体", "识别"):
            self.assertIn(bigram, tokens)

    def test_particles_split_runs_and_common_bigrams_are_dropped(self):
        tokens = ranking.tokenize("本文研究了数字人文的发展")
        self.assertNotIn("本文", tokens)
        self.assertNotIn("研究", tokens)
        self.assertNotIn("文的", tokens)
        self.assertNotIn("了数", tokens)
        self.assertIn("人文", tokens)

    def test_single_han_character_alone_is_not_a_token(self):
        self.assertEqual(ranking.tokenize("诗"), [])

    def test_fullwidth_latin_and_ideographic_space_fold_to_ascii(self):
        self.assertEqual(ranking.tokenize("ＢＥＲＴ　模型"), ["bert", "模型"])

    def test_cjk_punctuation_separates_runs(self):
        self.assertEqual(ranking.tokenize("乡村振兴，文旅"), ["乡村", "村振", "振兴", "文旅"])


class ChineseTitles(unittest.TestCase):
    def test_distinct_chinese_titles_get_distinct_keys(self):
        a = {"title": "数字人文视域下的古籍整理研究", "ids": {}}
        b = {"title": "乡村振兴战略下的农村金融发展", "ids": {}}
        self.assertNotEqual(sources.normalize_title(a["title"]), "")
        self.assertNotEqual(sources.key_of(a), sources.key_of(b))

    def test_chinese_title_normalization_ignores_punctuation_width_and_spacing(self):
        self.assertEqual(sources.normalize_title("《红楼梦》研究：ＡＩ 视角"),
                         sources.normalize_title("红楼梦 研究 ai视角"))


class ChinesePhrases(unittest.TestCase):
    def test_phrases_split_on_connectives_and_drop_frame_words(self):
        self.assertEqual(chtext.cjk_phrases("我想研究数字人文和古籍整理"), ["数字人文", "古籍整理"])
        self.assertEqual(chtext.cjk_phrases("偏向真实机器人"), ["真实机器人"])
        self.assertEqual(chtext.cjk_phrases("world model"), [])
        self.assertEqual(chtext.cjk_phrases("研究"), [])

    def test_overlong_runs_are_not_keywords(self):
        self.assertEqual(chtext.cjk_phrases("甲" * 17), [])


class Language(unittest.TestCase):
    def test_detect_language(self):
        self.assertEqual(chtext.detect_language("数字人文视域下的古籍整理"), "zh")
        self.assertEqual(chtext.detect_language("基于Transformer的古籍命名实体识别"), "zh")
        self.assertEqual(chtext.detect_language("World models for planning"), "en")
        self.assertEqual(chtext.detect_language("世界モデルによる計画"), "ja")
        self.assertEqual(chtext.detect_language("세계 모델"), "ko")
        self.assertEqual(chtext.detect_language("  123 "), "und")
        self.assertTrue(chtext.has_cjk("a 中 b"))
        self.assertFalse(chtext.has_cjk("naïve"))


class ChinesePinnedTermRanks(unittest.TestCase):
    def test_pinned_chinese_term_puts_matching_papers_first(self):
        pool = {
            "p1": "数字人文视域下的古籍整理研究 本文讨论数字人文方法在古籍整理中的应用",
            "p2": "乡村振兴战略下的农村金融发展 农村金融服务乡村振兴",
            "p3": "World models for robot planning",
            "p4": "基于数字人文的地方志知识图谱构建 地方志 数字人文 知识图谱",
            "p5": "高校思想政治教育的路径创新",
        }
        idf = ranking.build_idf([ranking.tokenize(t) for t in pool.values()])
        profile = ranking.rocchio([ranking.l2_normalize(ranking.vectorize(ranking.tokenize("数字人文"), idf))], [], [])
        scores = {k: ranking.cosine(profile, ranking.l2_normalize(ranking.vectorize(ranking.tokenize(t), idf)))
                  for k, t in pool.items()}
        ranked = sorted(scores, key=lambda k: -scores[k])
        self.assertEqual(set(ranked[:2]), {"p1", "p4"})
        self.assertEqual(scores["p3"], 0.0)


if __name__ == "__main__":
    unittest.main()

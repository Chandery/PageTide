"""Profile-led suggestions: pinned terms become categories, title phrases refine them."""
import unittest

from app.organization_facets import ALGORITHM, MAX_CHILDREN, suggest_groups

# A small library shaped like the owner's: almost everything is about world models,
# so a useful suggestion must split *inside* world models instead of by discipline.
PAPERS = [
    {"key": "jepa1", "title": "V-JEPA 2: Self-Supervised Video Models Enable Understanding and Planning",
     "abstract": "We train a world model with a joint embedding predictive architecture.", "topic": "Robotics"},
    {"key": "jepa2", "title": "Learning World Models with JEPA Objectives",
     "abstract": "A JEPA world model for control.", "topic": "Multimodal"},
    {"key": "wam1", "title": "World Action Model for Robot Manipulation",
     "abstract": "An action-conditioned world model.", "topic": "Robotics"},
    {"key": "wam2", "title": "Scaling World Action Model Pretraining",
     "abstract": "World models predict the effect of actions.", "topic": "GAN"},
    {"key": "vwm1", "title": "Video World Model for Driving",
     "abstract": "A generative video world model.", "topic": "Autonomous vehicles"},
    {"key": "vwm2", "title": "Long Horizon Video World Model",
     "abstract": "Video world models with memory.", "topic": "Computer vision"},
    {"key": "other", "title": "Protein Folding with Diffusion",
     "abstract": "Structure prediction.", "topic": "Biology"},
]


def by_name(result):
    return {group["name"]: group for group in result["groups"]}


class ProfileFacetTests(unittest.TestCase):
    def test_pinned_terms_are_top_categories_with_fine_children(self):
        result = suggest_groups(PAPERS, {"project": "WM", "pinned": ["world models", "JEPA"],
                                         "interest": ["action", "world", "model"]})
        self.assertEqual(result["algorithm"], ALGORITHM)
        groups = by_name(result)
        top = groups["世界模型"]
        self.assertIsNone(top["parent"])
        self.assertEqual(top["source"], "pinned")
        self.assertEqual(set(top["keys"]), {"jepa1", "jepa2", "wam1", "wam2", "vwm1", "vwm2"})
        self.assertIn("world models", top["reason"])
        # JEPA papers are all world-model papers, so JEPA is nested, not a sibling.
        self.assertEqual(groups["JEPA"]["parent"], top["id"])
        children = [g for g in result["groups"] if g["parent"] == top["id"]]
        self.assertLessEqual(len(children), MAX_CHILDREN)
        phrases = {g["name"] for g in children if g["source"] == "phrase"}
        self.assertIn("World Action Model", phrases)
        wam = groups["World Action Model"]["reason"]
        self.assertIn("含画像兴趣词 action", wam)
        self.assertNotIn("world", wam.split("兴趣词")[-1])
        video = next(g for g in children if g["name"].startswith("Video"))
        self.assertLessEqual({"vwm1", "vwm2"}, set(video["keys"]))
        # Discipline labels never become categories.
        self.assertFalse({"Robotics", "GAN", "Multimodal"} & set(groups))
        self.assertEqual(result["pending_keys"], ["other"])
        self.assertEqual(result["profile"]["project"], "WM")

    def test_without_pinned_terms_titles_still_give_fine_groups(self):
        result = suggest_groups(PAPERS, {"pinned": []})
        groups = by_name(result)
        self.assertIn("世界模型", groups)
        self.assertEqual(groups["世界模型"]["source"], "phrase")
        self.assertIn("还没有固定关键词", groups["世界模型"]["reason"])
        self.assertTrue(any(g["parent"] == groups["世界模型"]["id"] for g in result["groups"]))

    def test_chinese_glossary_term_matches_english_text(self):
        groups = by_name(suggest_groups(PAPERS, {"pinned": ["世界模型"]}))
        self.assertEqual(len(groups["世界模型"]["keys"]), 6)
        self.assertEqual(groups["世界模型"]["source"], "pinned")

    def test_rare_and_duplicate_pinned_terms_are_reported_not_invented(self):
        result = suggest_groups(PAPERS, {"pinned": ["world models", "world model", "diffusion", "quantum"]})
        unmatched = {u["term"]: u for u in result["profile"]["unmatched"]}
        self.assertEqual(unmatched["world model"]["same_as"], "world models")
        self.assertEqual(unmatched["diffusion"]["documents"], 1)
        self.assertEqual(unmatched["quantum"]["documents"], 0)
        names = [g["name"] for g in result["groups"]]
        self.assertEqual(names.count("世界模型"), 1)
        self.assertNotIn("quantum", names)

    def test_deterministic_and_ids_stable(self):
        profile = {"pinned": ["world models", "JEPA"]}
        first = suggest_groups(PAPERS, profile)
        self.assertEqual(first, suggest_groups(list(reversed(PAPERS)), profile))
        self.assertTrue(all(g["id"].startswith("facet-") for g in first["groups"]))
        self.assertEqual(len({g["id"] for g in first["groups"]}), len(first["groups"]))
        # Parents come before their children, which apply relies on.
        seen = set()
        for group in first["groups"]:
            self.assertTrue(group["parent"] is None or group["parent"] in seen)
            seen.add(group["id"])

    def test_invalid_profile_is_rejected(self):
        for profile in ("world", {"pinned": "world"}, {"pinned": [1]}, {"pinned": ["x" * 101]},
                        {"pinned": ["t%d" % i for i in range(41)]}):
            with self.assertRaises(ValueError):
                suggest_groups(PAPERS, profile)

    def test_matching_never_crosses_clause_punctuation(self):
        papers = [{"key": "r%d" % i, "title": "Legged robot control %d" % i,
                   "abstract": "Works in the real world. Model predictive control runs onboard."}
                  for i in range(3)] + PAPERS
        top = by_name(suggest_groups(papers, {"pinned": ["world models"]}))["世界模型"]
        self.assertFalse({"r0", "r1", "r2"} & set(top["keys"]))
        # Title phrases split at a colon too: "Models: Planning" is not "model planning".
        titles = [{"key": "c%d" % i, "title": "World Models: Planning Agents %d" % i} for i in range(3)]
        grams = {g["name"] for g in suggest_groups(titles)["groups"]}
        self.assertNotIn("Models Planning", grams)

    def test_version_numbers_are_not_clause_breaks(self):
        papers = [{"key": "a", "title": "Qwen2.5 for planning", "abstract": ""},
                  {"key": "b", "title": "Qwen2.5 agents", "abstract": "Built on Llama 3.1 too."},
                  {"key": "c", "title": "Llama 3.1 world model", "abstract": ""}]
        result = suggest_groups(papers, {"pinned": ["Qwen2.5", "Llama 3.1"]})
        self.assertEqual(set(by_name(result)["Qwen2.5"]["keys"]), {"a", "b"})
        self.assertEqual(set(by_name(result)["Llama 3.1"]["keys"]), {"b", "c"})

    def test_mixed_chinese_term_is_matched_exactly_not_by_its_latin_word(self):
        papers = [{"key": "a", "title": "LLM 推理 加速", "abstract": ""},
                  {"key": "b", "title": "llm 推理 benchmark", "abstract": ""},
                  {"key": "c", "title": "LLM agents for code", "abstract": ""},
                  {"key": "d", "title": "LLM safety", "abstract": ""}]
        groups = by_name(suggest_groups(papers, {"pinned": ["LLM 推理"]}))
        self.assertEqual(set(groups["LLM 推理"]["keys"]), {"a", "b"})

    def test_terms_over_the_category_limit_are_reported_not_dropped_silently(self):
        papers = [{"key": "%s%d" % (t, i), "title": "Topic%s study %d" % (t, i)}
                  for t in "abcdefghijklmn" for i in range(2)]
        result = suggest_groups(papers, {"pinned": ["Topic" + t for t in "abcdefghijklmn"]})
        tops = [g for g in result["groups"] if g["parent"] is None]
        self.assertEqual(len(tops), 12)
        dropped = [u for u in result["profile"]["unmatched"] if u.get("dropped")]
        self.assertEqual([u["term"] for u in dropped], ["Topicm", "Topicn"])
        self.assertEqual(dropped[0]["documents"], 2)

    def test_empty_library(self):
        result = suggest_groups([], {"pinned": ["world models"]})
        self.assertEqual(result["groups"], [])
        self.assertEqual(result["profile"]["unmatched"], [{"term": "world models", "documents": 0}])


if __name__ == "__main__":
    unittest.main()

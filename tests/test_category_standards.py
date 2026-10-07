"""Regression fixtures for the bilingual category standard; no private library."""
import unittest

from app.organization_facets import review, suggest_groups
from app.organization import Organization


PAPERS = [
    {"key": "a", "title": "Video World Model with Vision Transformers", "abstract": "World models for planning"},
    {"key": "b", "title": "Video World Model and World States", "abstract": "World model dynamics"},
    {"key": "c", "title": "Model for Embodied World States", "abstract": "World models use Vision Transformers"},
    {"key": "d", "title": "Model for Embodied World States", "abstract": "World model planning"},
]


class StandardTests(unittest.TestCase):
    def test_bilingual_duplicates_have_one_merge_and_one_target(self):
        dirs = [{"id": "en", "name": "World Models"}, {"id": "zh", "name": "世界模型"}]
        result = review(PAPERS, dirs, {"a": ["en"], "b": ["zh"]}, {})
        self.assertEqual(len(result["merges"]), 1)
        self.assertEqual({c["name"] for c in result["merges"][0]["copies"]}, {"World Models", "世界模型"})
        self.assertEqual(len({g["target"] for g in result["groups"] if g["target"]}), 1)

    def test_arbitrary_title_fragments_do_not_become_categories(self):
        result = suggest_groups(PAPERS, {"pinned": ["World Models"]})
        names = {g["name"] for g in result["groups"]}
        self.assertFalse({"World States", "Model for Embodied", "Embodied World States"} & names)
        self.assertIn("视频世界模型", names)
        method = next(g for g in result["groups"] if g["name"] == "视觉 Transformer")
        self.assertIsNotNone(method["parent"])

    def test_unknown_unpinned_phrase_remains_pending(self):
        papers = [{"key": k, "title": "Model for Embodied World States"} for k in ("a", "b")]
        result = suggest_groups(papers)
        self.assertEqual(result["groups"], [])
        self.assertEqual(result["pending_keys"], ["a", "b"])

    def test_selected_alias_reuses_existing_category(self):
        data = {"directions": [{"id": "en", "name": "World Models", "color": "#64748b"}],
                "memberships": {}, "protected": []}
        result = Organization._add_selected_suggestions(data, [{"id": "new", "name": "世界模型", "keys": ["a"], "parent": None}])
        self.assertEqual(result["created_categories"], 0)
        self.assertEqual(data["memberships"]["a"], ["en"])

    def test_distinct_concepts_and_different_levels_not_merged(self):
        dirs = [{"id": "a", "name": "Robotics"}, {"id": "b", "name": "具身智能"},
                {"id": "c", "name": "World Models"}, {"id": "d", "name": "世界模型", "parent_id": "c"}]
        self.assertEqual(review(PAPERS, dirs, {"a": ["a", "b", "c", "d"]}, {})["merges"], [])

    def test_custom_pinned_term_still_supported(self):
        papers = [{"key": k, "title": "World States for memory"} for k in ("a", "b")]
        result = suggest_groups(papers, {"pinned": ["World States"]})
        self.assertEqual([g["name"] for g in result["groups"]], ["World States"])

    def test_pinned_child_aliases_are_unique(self):
        groups = suggest_groups(PAPERS, {"pinned": ["world models", "video world model", "视频世界模型"]})['groups']
        self.assertEqual(len([g for g in groups if g['name'] == '视频世界模型']), 1)

    def test_new_child_cannot_reuse_unrelated_root_or_become_root(self):
        data = {"directions": [{"id": "root", "source_suggestion": "kid", "name": "JEPA", "color": "#64748b"}],
                "memberships": {}, "protected": []}
        with self.assertRaises(ValueError):
            Organization._add_selected_suggestions(data, [{"id": "kid", "name": "JEPA", "keys": ["a"], "parent": "missing"}])

    def test_parallel_bilingual_parents_and_children_merge_in_order(self):
        dirs = [{'id': 'en', 'name': 'World Models'}, {'id': 'zh', 'name': '世界模型'},
                {'id': 'a', 'name': 'JEPA', 'parent_id': 'en'}, {'id': 'b', 'name': 'JEPA', 'parent_id': 'zh'}]
        result = review(PAPERS, dirs, {'a': ['a'], 'b': ['b']}, {})
        self.assertEqual(len(result['merges']), 2)
        self.assertEqual(result['merges'][1]['depends_on'], [result['merges'][0]['id']])

    def test_related_independent_directions_not_nested_by_overlap(self):
        papers = [{'key': str(i), 'title': 'World model for robotics' if i < 2 else 'World model dynamics'} for i in range(4)]
        groups = suggest_groups(papers, {'pinned': ['world models', 'robotics']})['groups']
        robot = next(g for g in groups if g['name'] == '机器人')
        self.assertIsNone(robot['parent'])


if __name__ == "__main__":
    unittest.main()

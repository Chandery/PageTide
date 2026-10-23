"""Creation guidance follows the paper languages the person ticked (owner 2026-10-23: "勾选了汉语之后，创建还是使用英文").

Only 中文 ticked: Chinese keywords and queries, searched at Baidu and OpenAlex as Chinese; only 英文 or nothing: English as
before; both: a mix. The person's own items are never judged. Offline: the model is a fake, the network is a fake.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import guidance_contract as gc, ranking
from app.service import App
from tests.test_baidu_creation import Case, openalex_work

GOAL = '我想研究上古汉语和出土文献中的汉语历史语言学问题'
ZH_KEYWORDS = ['上古汉语', '汉语历史语言学', '汉语历史音韵学', '出土文献', '古文字学']
EN_KEYWORDS = ['Old Chinese', 'historical Chinese linguistics', 'Chinese historical phonology', 'excavated texts',
               'Chinese paleography']


def reply(keywords, queries, **extra):
    draft = {'keywords': keywords, 'queries': queries, 'ask': '', 'choices': [], 'summary': '上古汉语', 'ready': True}
    draft.update(extra)
    return {'ok': True, 'content': json.dumps({'reply': '已整理。', 'draft': draft}, ensure_ascii=False),
            'finish_reason': 'stop', 'usage': {'total_tokens': 10}}


class PromptTests(unittest.TestCase):
    def test_the_prompt_no_longer_hard_codes_english_terms(self):
        system = gc.SYSTEM
        self.assertNotIn('phrases in English', system)
        self.assertNotIn('5 English terms', system)
        self.assertIn('zh without en', system)
        self.assertIn('LLM 推理', system)
        self.assertIn('zh+en', system)
        self.assertIn('otherwise English', system)

    def test_the_prompt_stays_compact(self):
        self.assertLessEqual(len(gc.SYSTEM.encode('utf-8')), 1250)

    def test_the_language_choice_still_reaches_the_model_as_input(self):
        for chosen in (['zh'], ['en'], ['zh', 'en']):
            body = json.loads(gc.messages('目标', [], '目标', languages=chosen)[-1]['content'])
            self.assertEqual(body['languages'], chosen)


class VetTests(unittest.TestCase):
    def test_zh_only_keeps_chinese_keywords_and_drops_english_ones_when_a_chinese_one_exists(self):
        mixed = ['上古汉语', 'Old Chinese', 'LLM 推理', 'paleography']
        self.assertEqual(gc.vet_keywords(mixed, ['zh']), ['上古汉语', 'LLM 推理'])

    def test_zh_only_keeps_english_suggestions_rather_than_an_empty_draft(self):
        self.assertEqual(gc.vet_keywords(EN_KEYWORDS, ['zh']), EN_KEYWORDS)
        self.assertEqual(gc.vet_queries(['Old Chinese phonology'], ['zh']), ['Old Chinese phonology'])

    def test_zh_only_allows_two_chinese_queries(self):
        out = gc.vet_queries(['上古汉语 出土文献', '汉语历史音韵学', 'Old Chinese'], ['zh'])
        self.assertEqual(out, ['上古汉语 出土文献', '汉语历史音韵学'])

    def test_zh_only_with_only_english_queries_but_chinese_keywords_gets_a_query_from_the_keywords(self):
        self.assertEqual(gc.vet_queries(['Old Chinese phonology'], ['zh'], keywords=ZH_KEYWORDS), ['上古汉语 汉语历史语言学'])
        self.assertEqual(gc.vet_queries(['Old Chinese phonology'], ['zh'], keywords=EN_KEYWORDS), ['Old Chinese phonology'])

    def test_zh_plus_en_keeps_both_languages_with_at_most_one_chinese_query(self):
        self.assertEqual(gc.vet_keywords(['上古汉语', 'Old Chinese'], ['zh', 'en']), ['上古汉语', 'Old Chinese'])
        self.assertEqual(gc.vet_queries(['上古汉语', '出土文献', 'Old Chinese'], ['zh', 'en']), ['上古汉语', 'Old Chinese'])

    def test_zh_with_other_languages_than_en_counts_as_chinese_alone_and_other_languages_stay_english(self):
        self.assertEqual(gc.vet_keywords(['上古汉语', 'Old Chinese'], ['zh', 'ja']), ['上古汉语'])
        self.assertEqual(gc.vet_queries(['上古汉语', '出土文献', 'Old Chinese'], ['zh', 'la']), ['上古汉语', '出土文献'])
        for chosen in (['de'], ['en', 'de'], ['ja']):
            self.assertEqual(gc.vet_keywords(['上古汉语', 'Old Chinese'], chosen), ['Old Chinese'])
            self.assertEqual(gc.vet_queries(['上古汉语', 'Old Chinese'], chosen), ['Old Chinese'])

    def test_english_only_or_nothing_ticked_is_unchanged(self):
        for chosen in (['en'], [], None):
            self.assertEqual(gc.vet_keywords(['上古汉语', 'Old Chinese'], chosen), ['Old Chinese'])
            self.assertEqual(gc.vet_queries(['上古汉语', 'Old Chinese'], chosen), ['Old Chinese'])

    def test_the_query_built_from_chinese_keywords_is_chinese_and_short(self):
        self.assertEqual(gc.clean_queries([], ZH_KEYWORDS, languages=['zh']), ['上古汉语 汉语历史语言学'])
        self.assertEqual(gc.clean_queries([], ['Old Chinese', '上古汉语', '出土文献'], languages=['zh']), ['上古汉语 出土文献'])
        self.assertEqual(gc.clean_queries([], EN_KEYWORDS, languages=['zh']),
                         [' '.join(EN_KEYWORDS[:gc.QUERY_TERMS])])
        self.assertEqual(gc.clean_queries([], EN_KEYWORDS), [' '.join(EN_KEYWORDS[:gc.QUERY_TERMS])])


class TurnTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = App(root='.', data_dir=Path(self.temp.name))
        self.addCleanup(self.app.store.close)

    def quick(self, result, languages=('zh',), edits=None, mode='quick'):
        session = self.app.create_guidance_session('P', GOAL, mode)
        self.sid = session['id']
        shown = edits if edits is not None else {'keywords': session['draft']['keywords'], 'search_queries': []}
        with mock.patch.object(self.app.gateway, 'call', return_value=result) as call:
            out = self.app.guidance_turn(session['id'], GOAL, languages=list(languages), draft_edits=shown, base=0)
        self.sent = json.loads(call.call_args.args[1][-1]['content'])
        self.system = call.call_args.args[1][0]['content']
        return out['session']['draft'], out

    def test_zh_only_chinese_reply_gives_chinese_keywords_and_two_chinese_queries(self):
        draft, out = self.quick(reply(ZH_KEYWORDS, ['上古汉语 出土文献', '汉语历史音韵学']))
        self.assertEqual(out['mode'], 'ai')
        self.assertEqual(draft['keywords'], ZH_KEYWORDS)
        self.assertEqual(draft['search_queries'], ['上古汉语 出土文献', '汉语历史音韵学'])
        self.assertEqual(self.sent['languages'], ['zh'])

    def test_zh_only_english_reply_is_kept_not_left_empty(self):
        draft, _ = self.quick(reply(EN_KEYWORDS, ['Old Chinese phonology', 'excavated texts paleography']))
        self.assertEqual(draft['keywords'], EN_KEYWORDS)
        self.assertEqual(draft['search_queries'], ['Old Chinese phonology', 'excavated texts paleography'])

    def test_zh_only_chinese_keywords_with_english_queries_gets_a_chinese_query(self):
        draft, _ = self.quick(reply(ZH_KEYWORDS, ['Old Chinese phonology']))
        self.assertEqual(draft['search_queries'], ['上古汉语 汉语历史语言学'])

    def test_zh_only_a_missing_query_is_built_in_chinese_from_the_keywords(self):
        for queries in ([], [''], ['你想研究哪个朝代？']):
            with self.subTest(queries=queries):
                draft, _ = self.quick(reply(ZH_KEYWORDS, queries))
                self.assertEqual(draft['search_queries'], ['上古汉语 汉语历史语言学'])

    def test_a_quick_create_with_keywords_always_ends_with_a_query_whatever_the_languages(self):
        for languages in (['zh'], ['en'], ['zh', 'en'], []):
            for keywords in (ZH_KEYWORDS, EN_KEYWORDS, ZH_KEYWORDS[:2] + EN_KEYWORDS[:2]):
                for queries in ([], ['？'], ['x?']):
                    if keywords is ZH_KEYWORDS and 'zh' not in languages:
                        continue   # Chinese suggestions without 中文 ticked are dropped by design
                    with self.subTest(languages=languages, keywords=keywords, queries=queries):
                        draft, _ = self.quick(reply(keywords, queries), languages=languages)
                        self.assertTrue(draft['keywords'], draft)
                        self.assertTrue(draft['search_queries'], draft)

    def test_zh_plus_en_keeps_a_mix(self):
        draft, _ = self.quick(reply(['上古汉语', '出土文献', 'Old Chinese', 'excavated texts', 'paleography'],
                                    ['上古汉语 出土文献', '汉语历史音韵学', 'Old Chinese phonology']), languages=['zh', 'en'])
        self.assertEqual(draft['keywords'], ['上古汉语', '出土文献', 'Old Chinese', 'excavated texts', 'paleography'])
        self.assertEqual(draft['search_queries'], ['上古汉语 出土文献', 'Old Chinese phonology'])

    def test_english_only_reply_with_chinese_suggestions_drops_them(self):
        draft, _ = self.quick(reply(['上古汉语', 'Old Chinese'], ['上古汉语', 'Old Chinese phonology']), languages=['en'])
        self.assertEqual((draft['keywords'], draft['search_queries']), (['Old Chinese'], ['Old Chinese phonology']))

    def test_the_persons_own_english_items_survive_a_zh_only_turn(self):
        draft, _ = self.quick(reply(ZH_KEYWORDS, ['上古汉语 出土文献']),
                              edits={'keywords': ['my English term'], 'search_queries': ['my english query']})
        self.assertEqual(draft['keywords'], ['my English term', *ZH_KEYWORDS])
        self.assertEqual(draft['search_queries'], ['my english query', '上古汉语 出土文献'])

    def test_a_deleted_or_own_chinese_item_does_not_make_the_english_ones_vanish(self):
        # the person deleted the model's Chinese keyword and query; the model offers it again beside English ones
        first, _ = self.quick(reply(['上古汉语', '出土文献'], ['上古汉语 出土文献']), mode='ai_guided')
        session = self.app.guidance_session_view(self.sid)
        kept_keywords, kept_queries = ['出土文献'], []
        with mock.patch.object(self.app.gateway, 'call',
                               return_value=reply(['上古汉语', 'Old Chinese', 'paleography'], ['上古汉语 出土文献', 'Old Chinese phonology'])):
            out = self.app.guidance_turn(session['id'], '继续', languages=['zh'], base=session['draft']['revision'],
                                         draft_edits={'keywords': kept_keywords, 'search_queries': kept_queries})
        draft = out['session']['draft']
        self.assertEqual(draft['keywords'], ['Old Chinese', 'paleography'])   # 上古汉语 stays deleted; the model's old 出土文献 is replaced
        self.assertEqual(draft['search_queries'], ['Old Chinese phonology'])

    def test_a_later_turn_replaces_the_earlier_english_queries_with_one_built_from_chinese_keywords(self):
        self.quick(reply(EN_KEYWORDS, ['Old Chinese phonology']), mode='ai_guided')
        session = self.app.guidance_session_view(self.sid)
        page = {'keywords': session['draft']['keywords'], 'search_queries': session['draft']['search_queries']}
        with mock.patch.object(self.app.gateway, 'call', return_value=reply(ZH_KEYWORDS, ['Old Chinese phonology'])):
            out = self.app.guidance_turn(session['id'], '继续', languages=['zh'], base=session['draft']['revision'], draft_edits=page)
        self.assertEqual(out['session']['draft']['search_queries'], ['上古汉语 汉语历史语言学'])
        self.assertEqual(out['session']['draft']['keywords'], ZH_KEYWORDS)

    def test_the_chat_text_language_still_follows_the_interface(self):
        self.quick(reply(ZH_KEYWORDS, []))
        self.assertTrue(self.system.endswith('Text in Chinese.'))


class SearchTests(Case):
    """The queries a zh-only quick create produces are what the candidate search sends to Baidu and OpenAlex."""

    def test_zh_only_quick_create_searches_baidu_and_openalex_with_the_chinese_queries(self):
        self.set_user_settings(self.app, timePreference='all', sourceBaiduScholar=True)
        self.net.openalex_results = [openalex_work(7, '上古汉语研究')]
        session = self.app.create_guidance_session('P', GOAL, 'quick')
        result = reply(ZH_KEYWORDS, ['上古汉语 出土文献', '汉语历史音韵学'])
        with mock.patch.object(self.app.gateway, 'call', return_value=result):
            self.app.guidance_turn(session['id'], GOAL, languages=['zh'], base=0,
                                   draft_edits={'keywords': session['draft']['keywords'], 'search_queries': []})
        with self.patched():
            out = self.app.guidance_preview(session['id'], languages=['zh'])
        self.assertEqual(sorted(c['wd'] for c in self.net.baidu), ['上古汉语 出土文献', '汉语历史音韵学'])
        self.assertGreaterEqual(len(self.net.openalex), 1)
        self.assertTrue(any('%E4%B8%8A%E5%8F%A4' in url for url in self.net.openalex), self.net.openalex)
        self.assertTrue(out['items'])


class DownstreamTests(unittest.TestCase):
    def test_chinese_project_keywords_match_chinese_papers_in_local_ranking(self):
        keyword = '上古汉语'
        self.assertTrue({'上古', '古汉', '汉语'} <= set(ranking.tokenize(keyword)))
        self.assertTrue(ranking.term_in_text('上古汉语的动词研究', keyword))
        self.assertFalse(ranking.term_in_text('现代汉语语法', keyword))
        docs = [ranking.tokenize(text) for text in ('上古汉语的动词研究', '知识图谱构建方法', 'Old Chinese verbs')]
        idf = ranking.build_idf(docs)
        profile = ranking.l2_normalize(ranking.vectorize(ranking.tokenize(' '.join(['上古汉语', '出土文献'])), idf))
        scores = [ranking.cosine(profile, ranking.l2_normalize(ranking.vectorize(d, idf))) for d in docs]
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[0], scores[2])

    def test_project_keywords_in_chinese_reach_the_pinned_terms_the_profile_uses(self):
        with tempfile.TemporaryDirectory() as temp:
            app = App(root='.', data_dir=Path(temp))
            self.addCleanup(app.store.close)
            project_id = app.create_project('中文项目', 'ai_guided', ZH_KEYWORDS)['project_id']
            self.assertEqual(app.profile(project_id)['pinned_terms'], ZH_KEYWORDS)
            self.assertEqual(app._project_keywords(project_id), ZH_KEYWORDS)


if __name__ == '__main__':
    unittest.main()

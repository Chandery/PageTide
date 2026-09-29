"""Local multilingual lexical features and conservative Chinese display labels.

The glossary ONLY names a computed group; it does not assign disciplines or
translate arbitrary text. Unknown names remain explicitly editable placeholders.
"""
import re
from collections import Counter
from . import ranking

GENERIC = ranking.STOPWORDS | set('''study studies research analysis analyses present presented
result findings demonstrate demonstrated significant performance framework system systems
novel effective efficient evaluation evaluate evaluated experimental experiments experiment
data dataset datasets task tasks technique techniques application applications investigation
investigate investigated article review comprehensive development developed development
potential challenges different several through across including provide provides proposed
approaches methods conclusion conclusions objective objectives background introduction
observed observations effect effects evidence compared comparison improving improved'''.split())
ZH_GENERIC = {'研究', '方法', '分析', '结果', '本文', '通过', '提出', '基于', '应用', '影响', '评价', '进行', '发展'}
# Display vocabulary, deliberately not a taxonomy or a classification fallback.
LABELS = {
    'world model': '世界模型', 'world models': '世界模型',
    'reinforcement learning': '强化学习', 'machine learning': '机器学习',
    'deep learning': '深度学习', 'neural network': '神经网络',
    'language model': '语言模型', 'language models': '语言模型',
    'robot': '机器人', 'robots': '机器人', 'robotics': '机器人',
    'autonomous driving': '自动驾驶', 'video generation': '视频生成',
    'cancer': '肿瘤研究', 'immunotherapy': '免疫治疗', 'genomics': '基因组学',
    'protein': '蛋白质研究', 'proteins': '蛋白质研究', 'neuroscience': '神经科学',
    'climate change': '气候变化', 'biodiversity': '生物多样性', 'ecology': '生态学',
    'quantum': '量子研究', 'superconductivity': '超导研究', 'catalysis': '催化研究',
    'battery': '电池研究', 'batteries': '电池研究',
    'economics': '经济学', 'education': '教育研究', 'psychology': '心理学',
    'archaeology': '考古学', 'linguistics': '语言学', 'comparative literature': '比较文学',
    'manuscript': '手稿研究', 'manuscripts': '手稿研究', 'philology': '语文学',
}


def tokenize(text):
    text = text.lower()
    words = re.findall(r"[^\W_]+", text, re.UNICODE)
    # Latin and other alphabetic scripts; CJK is handled as overlapping features.
    words = [w for w in words if not re.search(r'[\u3400-\u9fff]', w)]
    tokens = [w for w in words if len(w) >= 3 and w not in GENERIC and not w.isdigit()]
    tokens += [a + ' ' + b for a, b in zip(words, words[1:])
               if a not in GENERIC and b not in GENERIC and len(a) >= 3 and len(b) >= 3
               and not a.isdigit() and not b.isdigit()]
    # Keep meaningful established phrases even when one word is generic.
    tokens += [term for term in LABELS if ' ' in term and
               re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text)]
    for run in re.findall(r'[\u3400-\u9fff]+', text):
        tokens += [run[i:i + size] for size in (2, 3, 4)
                   for i in range(len(run) - size + 1)
                   if not any(stop in run[i:i + size] for stop in ZH_GENERIC)]
    return tokens


def features(row):
    return (tokenize(row['title']) * 2 + tokenize(row['topic']) * 4 +
            tokenize(row['abstract']))


def describe(members, rows, index):
    documents = [set(tokenize(rows[key]['title'] + ' ' + rows[key]['topic'])) for key in members]
    counts = Counter(term for document in documents for term in document)
    shared = [term for term in counts if counts[term] >= max(2, (len(members) + 1) // 2)]
    shared.sort(key=lambda term: (-counts[term], -len(term.split()), -len(term), term))
    labels = []
    for term in shared:
        label = LABELS.get(term) or (term if term in set(LABELS.values()) else None)
        if label and label not in labels:
            labels.append(label)
    terms = shared[:5]
    if not terms:
        abstract_counts = Counter(term for key in members for term in set(tokenize(rows[key]['abstract'])))
        terms = sorted((term for term in abstract_counts if abstract_counts[term] >= 2),
                       key=lambda term: (-abstract_counts[term], -len(term.split()), term))[:5]
    if labels:
        name = ' · '.join(labels[:2])
    else:
        name = '相关主题 %d（待命名）' % index
    return name, terms, ('依据标题、摘要与主题的共同词汇归并；请核对论文内容。'
                         if labels or '待命名' not in name else
                         '已按共同词汇归并；暂无可靠中文名称，请根据原文关键词命名。')

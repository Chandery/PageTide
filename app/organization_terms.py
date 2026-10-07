"""Exact bilingual identities and conservative category vocabulary.

Matching evidence is separate from identity: related fields and similar paper
sets never make two categories synonyms. Unknown owner names remain unchanged.
"""
import re
import unicodedata

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


def _normal(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value or '')).casefold().split())


# Broad directions may stand alone. Methods refine a supported direction;
# explicit pinned keywords remain an owner choice even outside this vocabulary.
TERMS = []
for _english, _chinese in LABELS.items():
    _existing = next((t for t in TERMS if t['zh'] == _chinese), None)
    if _existing:
        _existing['aliases'].append(_english)
    else:
        TERMS.append({'id': _english.replace(' ', '-'), 'en': _english.title(),
                      'zh': _chinese, 'aliases': [_english, _chinese], 'kind': 'direction', 'parent': None})


def _term(identifier, english, chinese, aliases=(), kind='direction', parent=None):
    TERMS.append({'id': identifier, 'en': english, 'zh': chinese,
                  'aliases': list(dict.fromkeys([english, chinese, *aliases])), 'kind': kind, 'parent': parent})


_term('video-world-model', 'Video World Models', '视频世界模型', ['video world model'], parent='world-model')
_term('world-action-model', 'World Action Models', '世界动作模型', ['world action model'], parent='world-model')
_term('latent-world-model', 'Latent World Models', '潜空间世界模型', ['latent world model', 'latent space world model'], parent='world-model')
_term('model-based-rl', 'Model-based Reinforcement Learning', '基于模型的强化学习', ['model based RL'], parent='reinforcement-learning')
_term('embodied-intelligence', 'Embodied Intelligence', '具身智能')
_term('robot-manipulation', 'Robot Manipulation', '机器人操作', ['robotic manipulation'], parent='robot')
_term('representation-learning', 'Representation Learning', '表征学习')
_term('jepa', 'JEPA', 'JEPA', ['joint embedding predictive architecture', 'joint-embedding predictive architecture'], kind='method')
_term('vision-transformer', 'Vision Transformers', '视觉 Transformer', ['vision transformer', 'ViT', '视觉变换器'], kind='method')
_term('3d-gaussian-splatting', '3D Gaussian Splatting', '三维高斯泼溅', ['3DGS', '3D GS', '三维高斯溅射'], kind='method')
_term('diffusion-model', 'Diffusion Models', '扩散模型', ['diffusion model'], kind='method')

for _t in TERMS:
    if _t['id'] in {'neural-network', 'deep-learning', 'machine-learning'}:
        _t['kind'] = 'method'
        _t['auto'] = False

BY_ID = {t['id']: t for t in TERMS}
ALIASES = {_normal(alias): t['id'] for t in TERMS for alias in t['aliases']}


def category_identity(name):
    normalized = _normal(name)
    if normalized in ALIASES:
        return 'term:' + ALIASES[normalized]
    # A bilingual display label is an alias only if EVERY part says the same thing.
    parts = [p.strip() for p in re.split(r'\s*/\s*|\s*\|\s*', normalized) if p.strip()]
    identities = {ALIASES.get(p) for p in parts}
    if len(parts) > 1 and len(identities) == 1 and None not in identities:
        return 'term:' + next(iter(identities))
    return 'custom:' + normalized


def category_term(name):
    identity = category_identity(name)
    return BY_ID.get(identity[5:]) if identity.startswith('term:') else None


def category_label(name, language='zh-CN'):
    term = category_term(name)
    return term['en' if language == 'en-US' else 'zh'] if term else str(name or '')


def category_aliases(name):
    term = category_term(name)
    return list(term['aliases']) if term else [str(name or '')]

"""Conservative Chinese display names for suggested categories.

The glossary ONLY names a phrase the suggestion already found; it does not
assign disciplines or translate arbitrary text. Unknown phrases keep the
original wording from the paper titles.
"""
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

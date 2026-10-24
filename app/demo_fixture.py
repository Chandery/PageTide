"""The built-in data of the demo project (the onboarding tour). Pure data: nothing here reads a file, the network or a clock.

Provenance (read this before trusting any text below):
  * Identifiers, titles and first-version dates are public arXiv metadata written from memory. They were NOT re-checked
    against arXiv: the sandbox that wrote this file had no access to export.arxiv.org (ABSTRACTS_VERIFIED below).
  * The `abstract` of every paper is the author's own SHORT PARAPHRASE of what the paper says, not the verbatim arXiv
    abstract. They exist so the demo's local ranking, profile terms and graph have text to work with.
  * The one-line previews (PREVIEWS) are hand-written for the demo in both languages. They are not model output; the
    demo labels them as pre-written.
The demo project is Transformer lineage on purpose: it has nothing to do with the topic of a person's real project.

Roles:  "candidate" = one of today's five recommendations (unrated);
        "useful" = saved with a 有用 label at `days_ago` days before the sandbox was made, optionally with a familiarity
        mark ("understood" / "too_hard") at `marks` = [(action, days_ago), ...];
        "irrelevant" = explicitly marked 不相关 (not saved).
`days_ago` is relative to the moment the sandbox is built, so the weekly report always has a current and a previous
week. Weeks are UTC calendar days ending tomorrow: the current week holds days_ago <= 5, the previous one 7.1 to 12.
"""
import hashlib
import json

PROJECT_ID = "pdh-demo"
ABSTRACTS_VERIFIED = False   # see the header: paraphrases, identifiers from memory

NAME = {"zh": "演示项目", "en": "Demo project"}

# The final pinned terms; they are also the project's keywords (pinning rewrites the keywords).
KEYWORDS = ["transformer", "attention", "instruction tuning"]
# The pin history, oldest first: (terms, days_ago). The last entry is KEYWORDS.
PIN_HISTORY = [(["transformer"], 21.5), (["transformer", "attention"], 12.5), (KEYWORDS, 2.5)]

DIRECTIONS = [
    {"id": "lm", "color": "#167b70", "name": {"zh": "预训练语言模型", "en": "Pretrained language models"}},
    {"id": "vit", "color": "#3b6fb6", "name": {"zh": "视觉 Transformer", "en": "Vision Transformers"}},
    {"id": "eff", "color": "#b5651d", "name": {"zh": "高效注意力与长上下文", "en": "Efficient attention and long context"}},
    {"id": "align", "color": "#8a4fa0", "name": {"zh": "对齐与指令微调", "en": "Alignment and instruction tuning"}},
]


def _p(arxiv_id, title, published, authors, abstract, role, direction=None, days_ago=None, marks=()):
    return {"arxiv_id": arxiv_id, "title": title, "published": published, "authors": list(authors), "abstract": abstract,
            "role": role, "direction": direction, "days_ago": days_ago, "marks": list(marks)}


PAPERS = [
    # ---- today's five (unrated) ------------------------------------------------------------------------------
    _p("1706.03762", "Attention Is All You Need", "2017-06-12", ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
       "Sequence models used to be built on recurrent or convolutional networks. This paper proposes the Transformer, an "
       "architecture made only of attention layers with no recurrence and no convolution. On machine translation it "
       "reaches better quality than earlier systems, trains in a fraction of the time because attention can be computed "
       "in parallel, and also transfers to parsing.", "candidate"),
    _p("1810.04805", "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding", "2018-10-11",
       ["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee"],
       "BERT pre-trains a deep bidirectional Transformer on unlabeled text by predicting masked words and whether two "
       "sentences follow each other. The pre-trained model is then fine-tuned with one small extra layer and improves a "
       "wide range of language understanding benchmarks, including question answering and inference.", "candidate"),
    _p("2001.08361", "Scaling Laws for Neural Language Models", "2020-01-23", ["Jared Kaplan", "Sam McCandlish", "Tom Henighan"],
       "The loss of a language model follows smooth power laws in model size, dataset size and training compute, over "
       "many orders of magnitude. Other architectural details matter little. The fitted laws suggest how to split a "
       "fixed compute budget, and that larger models are more sample efficient.", "candidate"),
    _p("2005.14165", "Language Models are Few-Shot Learners", "2020-05-28", ["Tom B. Brown", "Benjamin Mann", "Nick Ryder"],
       "Scaling a language model to 175 billion parameters lets it perform many tasks from a few examples given in the "
       "prompt, with no gradient update. The paper evaluates this few-shot ability on translation, question answering, "
       "arithmetic and more, and also discusses where it fails and the risks of such a model.", "candidate"),
    _p("2010.11929", "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale", "2020-10-22",
       ["Alexey Dosovitskiy", "Lucas Beyer", "Alexander Kolesnikov"],
       "A pure Transformer applied to a sequence of image patches can classify images without convolutions. When "
       "pre-trained on large datasets and transferred to smaller benchmarks, this Vision Transformer matches or beats "
       "strong convolutional networks while needing fewer computing resources to train.", "candidate"),
    # ---- pretrained language models --------------------------------------------------------------------------
    _p("1906.08237", "XLNet: Generalized Autoregressive Pretraining for Language Understanding", "2019-06-19",
       ["Zhilin Yang", "Zihang Dai", "Yiming Yang"],
       "XLNet is a pretrained language model that learns bidirectional context by pretraining on every permutation of "
       "the word order instead of masking tokens. Built on a Transformer with longer memory, it improves language "
       "understanding benchmarks over BERT after fine-tuning, including question answering and reading comprehension.", "useful", "lm", 26.4),
    _p("1909.11942", "ALBERT: A Lite BERT for Self-supervised Learning of Language Representations", "2019-09-26",
       ["Zhenzhong Lan", "Mingda Chen", "Sebastian Goodman"],
       "ALBERT is a lighter pretrained language model: parameter sharing across layers and a factorized embedding "
       "shrink BERT, and a sentence-order loss replaces next-sentence prediction. Pretraining the smaller model is "
       "faster, and fine-tuning it still improves language understanding benchmarks.", "useful", "lm", 25.2),
    _p("1910.13461", "BART: Denoising Sequence-to-Sequence Pre-training for Natural Language Generation, Translation, and Comprehension",
       "2019-10-29", ["Mike Lewis", "Yinhan Liu", "Naman Goyal"],
       "BART is a pretrained sequence-to-sequence language model: pretraining corrupts the text with several noising "
       "schemes and learns to reconstruct it. After fine-tuning it matches RoBERTa on language understanding "
       "benchmarks and sets new results on summarization and dialogue generation.", "useful", "lm", 24.1),
    _p("1910.10683", "Exploring the Limits of Transfer Learning with a Unified Text-to-Text Transformer", "2019-10-23",
       ["Colin Raffel", "Noam Shazeer", "Adam Roberts"],
       "T5 pretrains one text-to-text Transformer language model and compares pretraining objectives, architectures "
       "and data on language understanding benchmarks. Scaling the pretraining corpus and the model, then fine-tuning "
       "on summarization, question answering and classification, gives strong benchmark results.", "useful", "lm", 22.7,
       marks=[("understood", 8.0)]),
    _p("2003.10555", "ELECTRA: Pre-training Text Encoders as Discriminators Rather Than Generators", "2020-03-23",
       ["Kevin Clark", "Minh-Thang Luong", "Quoc V. Le"],
       "ELECTRA is pretrained as a discriminator: instead of masking tokens it learns to detect which tokens a small "
       "generator replaced. Pretraining over every token is more efficient than masked language modeling, and fine- "
       "tuning gives better language understanding benchmark results than BERT at the same compute.", "useful", "lm", 21.3),
    _p("1907.11692", "RoBERTa: A Robustly Optimized BERT Pretraining Approach", "2019-07-26",
       ["Yinhan Liu", "Myle Ott", "Naman Goyal"],
       "RoBERTa revisits BERT pretraining and finds the language model was undertrained. Pretraining longer with "
       "bigger batches on more tokens, with dynamic masking and no next-sentence objective, improves language "
       "understanding benchmarks after fine-tuning.", "useful", "lm", 18.9, marks=[("understood", 1.8)]),
    _p("2203.15556", "Training Compute-Optimal Large Language Models", "2022-03-29",
       ["Jordan Hoffmann", "Sebastian Borgeaud", "Arthur Mensch"],
       "For a fixed compute budget, a pretrained language model should grow in parameters and in training tokens in "
       "equal proportion. Earlier large language models were undertrained; Chinchilla, smaller but pretrained on more "
       "tokens, beats them on language understanding benchmarks with the same compute.", "useful", "lm", 17.4),
    # ---- vision Transformers -----------------------------------------------------------------------------------
    _p("2103.14030", "Swin Transformer: Hierarchical Vision Transformer using Shifted Windows", "2021-03-25",
       ["Ze Liu", "Yutong Lin", "Yue Cao"],
       "Swin is a hierarchical vision Transformer: self-attention runs inside shifted windows of image patches and "
       "patches merge across stages. Cost grows linearly with image size, and the visual backbone works for image "
       "recognition, detection and segmentation.", "useful", "vit", 16.8, marks=[("understood", 7.6)]),
    _p("2012.12877", "Training data-efficient image transformers & distillation through attention", "2020-12-23",
       ["Hugo Touvron", "Matthieu Cord", "Matthijs Douze"],
       "DeiT trains a vision Transformer for image recognition on ImageNet alone, using a stronger training recipe and "
       "a distillation token that learns from a convolutional teacher through attention. Image patches are processed "
       "by the Transformer without any large external dataset.", "useful", "vit", 15.9),
    _p("2103.00020", "Learning Transferable Visual Models From Natural Language Supervision", "2021-02-26",
       ["Alec Radford", "Jong Wook Kim", "Chris Hallacy"],
       "CLIP pretrains an image encoder and a text encoder to match images with captions on web data. The visual model "
       "recognizes images zero-shot from text descriptions of the classes and transfers across image recognition tasks "
       "without task-specific training.", "useful", "vit", 3.0),
    _p("2111.06377", "Masked Autoencoders Are Scalable Vision Learners", "2021-11-11",
       ["Kaiming He", "Xinlei Chen", "Saining Xie"],
       "A masked autoencoder hides most image patches and reconstructs them. The vision Transformer encoder sees only "
       "the visible patches, which makes pretraining fast and lets large visual models learn good representations for "
       "image recognition from images alone.", "useful", "vit", 11.8),
    _p("2105.01601", "MLP-Mixer: An all-MLP Architecture for Vision", "2021-05-04",
       ["Ilya Tolstikhin", "Neil Houlsby", "Alexander Kolesnikov"],
       "MLP-Mixer is an image recognition architecture built only from multilayer perceptrons that mix information "
       "across image patches and across channels, with no convolution and no attention. At large scale it is "
       "competitive with vision Transformers.", "irrelevant", "vit", 11.2),
    _p("2005.12872", "End-to-End Object Detection with Transformers", "2020-05-26", ["Nicolas Carion", "Francisco Massa", "Gabriel Synnaeve"],
       "DETR casts object detection in images as direct set prediction with a Transformer encoder-decoder and removes "
       "hand-designed components such as anchors. It matches strong detection baselines and extends to segmentation.", "irrelevant", "vit", 10.4),
    # ---- efficient attention and long context -----------------------------------------------------------------
    _p("2004.05150", "Longformer: The Long-Document Transformer", "2020-04-10", ["Iz Beltagy", "Matthew E. Peters", "Arman Cohan"],
       "Longformer makes attention efficient for long documents: a sliding window plus a few global tokens makes the "
       "cost linear in sequence length instead of quadratic. It processes long sequences with less memory and improves "
       "long document question answering and summarization.", "useful", "eff", 9.7),
    _p("2001.04451", "Reformer: The Efficient Transformer", "2020-01-13", ["Nikita Kitaev", "Lukasz Kaiser", "Anselm Levskaya"],
       "Reformer makes Transformers efficient on long sequences: locality-sensitive hashing replaces dot-product "
       "attention so the cost drops from quadratic to near-linear in sequence length, and reversible layers cut "
       "memory. Quality stays close to the standard model.", "useful", "eff", 9.1),
    _p("2006.04768", "Linformer: Self-Attention with Linear Complexity", "2020-06-08", ["Sinong Wang", "Belinda Z. Li", "Madian Khabsa"],
       "Linformer shows the attention matrix is low rank and projects keys and values to a shorter length, so self- "
       "attention costs linear time and memory in sequence length. Efficient attention on long sequences stays close "
       "to standard Transformer quality.", "useful", "eff", 8.4),
    _p("2009.14794", "Rethinking Attention with Performers", "2020-09-30", ["Krzysztof Choromanski", "Valerii Likhosherstov", "David Dohan"],
       "Performers approximate softmax attention with random features, giving efficient attention whose cost and "
       "memory are linear in sequence length, with provable estimates and no sparsity or low-rank assumption. They "
       "work on long sequences of text, images and proteins.", "useful", "eff", 7.3, marks=[("too_hard", 3.8)]),
    _p("2205.14135", "FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness", "2022-05-27",
       ["Tri Dao", "Daniel Y. Fu", "Stefano Ermon"],
       "FlashAttention computes exact attention efficiently by tiling it so that data stays in fast on-chip memory, "
       "reducing reads and writes to slow GPU memory. It is faster and uses less memory than standard attention, which "
       "makes long sequences practical.", "useful", "eff", 4.6),
    _p("2104.09864", "RoFormer: Enhanced Transformer with Rotary Position Embedding", "2021-04-20", ["Jianlin Su", "Yu Lu", "Shengfeng Pan"],
       "RoFormer encodes position with rotary embeddings so attention over long sequences depends on relative "
       "distance: query and key vectors are rotated, which handles flexible sequence length with efficient memory "
       "growth and improves long text classification at unchanged attention cost.", "useful", "eff", 4.1),
    # ---- alignment and instruction tuning ---------------------------------------------------------------------
    _p("2109.01652", "Finetuned Language Models Are Zero-Shot Learners", "2021-09-03", ["Jason Wei", "Maarten Bosma", "Vincent Y. Zhao"],
       "Instruction tuning fine-tunes a language model on many tasks written as natural language instructions, which "
       "improves zero-shot performance on unseen tasks. The gain from instructions grows with model size and with the "
       "number of instruction tasks.", "useful", "align", 2.7),
    _p("2201.11903", "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models", "2022-01-28",
       ["Jason Wei", "Xuezhi Wang", "Dale Schuurmans"],
       "Chain-of-thought prompting gives a language model instructions in the prompt as a few examples with reasoning "
       "steps. The large model then writes its own steps, improving arithmetic and commonsense reasoning with no human "
       "feedback or fine-tuning, so the instructions alone steer its behaviour.", "useful", "align", 2.1),
    _p("2203.02155", "Training language models to follow instructions with human feedback", "2022-03-04",
       ["Long Ouyang", "Jeff Wu", "Xu Jiang"],
       "Larger language models do not follow user instructions better by default. Fine-tuning a language model on "
       "human demonstrations and then using reinforcement learning from human feedback on preference rankings yields a "
       "smaller model that follows instructions and is preferred by people.", "useful", "align", 3.3),
    _p("2212.08073", "Constitutional AI: Harmlessness from AI Feedback", "2022-12-15", ["Yuntao Bai", "Saurav Kadavath", "Sandipan Kundu"],
       "Constitutional AI aligns a language model for harmlessness with a short written list of principles instead of "
       "human labels: the model critiques and revises its answers, then reinforcement learning uses AI feedback from a "
       "preference model, with less human feedback.", "useful", "align", 1.4),
    _p("2305.18290", "Direct Preference Optimization: Your Language Model is Secretly a Reward Model", "2023-05-29",
       ["Rafael Rafailov", "Archit Sharma", "Eric Mitchell"],
       "Direct preference optimization aligns a language model to human preferences without a separate reward model or "
       "reinforcement learning: a simple classification loss on preference pairs optimizes the same objective, "
       "matching human feedback pipelines with more stable, cheaper training.", "useful", "align", 0.9,
       marks=[("too_hard", 0.6)]),
]

# Pre-written one-line previews, one per paper: {arxiv_id: {"zh": {...}, "en": {...}}} with the triage contract's three
# fields. They are written for the demo and say so; none of them is model output.
PREVIEWS = {
    "1706.03762": {
        "zh": {"one_liner": "提出只用注意力、不用循环和卷积的 Transformer，训练更快、翻译更好。",
               "why_relevant": "演示画像里的“transformer”“attention”两个词主要来自这篇。",
               "caution": "实验以机器翻译为主，其他任务的效果要看后续工作。"},
        "en": {"one_liner": "Introduces the Transformer, built on attention alone with no recurrence or convolution, which trains faster and translates better.",
               "why_relevant": "The demo profile's terms \"transformer\" and \"attention\" mostly come from this paper.",
               "caution": "The experiments are mainly machine translation; results on other tasks come from later work."}},
    "1810.04805": {
        "zh": {"one_liner": "用遮盖词预测预训练双向 Transformer，再加一层微调，刷新多项理解任务。",
               "why_relevant": "你收藏的预训练语言模型方向（RoBERTa、ALBERT、ELECTRA）都是在它的基础上改进的。",
               "caution": "只做理解类任务，不擅长生成；预训练成本很高。"},
        "en": {"one_liner": "Pre-trains a bidirectional Transformer by predicting masked words, then fine-tunes it with one extra layer to lift many understanding tasks.",
               "why_relevant": "The pretrained-language-model papers you saved (RoBERTa, ALBERT, ELECTRA) all build on it.",
               "caution": "It targets understanding tasks rather than generation, and pretraining is expensive."}},
    "2001.08361": {
        "zh": {"one_liner": "语言模型的损失随模型、数据、算力呈平滑的幂律下降，可据此分配训练预算。",
               "why_relevant": "它是你收藏的 Chinchilla 一文的前提，两篇的结论可以对照着读。",
               "caution": "后来的工作修正了其中模型与数据的最优比例，别当成定论。"},
        "en": {"one_liner": "Language-model loss falls as a smooth power law in model size, data and compute, which guides how to spend a training budget.",
               "why_relevant": "It is the starting point of the Chinchilla paper you saved; the two read well side by side.",
               "caution": "Later work revised its optimal split of model size and data, so do not treat it as final."}},
    "2005.14165": {
        "zh": {"one_liner": "把语言模型放大到 1750 亿参数后，只靠提示里的几个例子就能完成很多任务。",
               "why_relevant": "与你最近收藏的指令微调、思维链几篇是同一条线：怎样让大模型听懂任务。",
               "caution": "少样本效果不稳定，文中也讨论了它的局限与风险。"},
        "en": {"one_liner": "Scales a language model to 175B parameters so that a few examples in the prompt are enough for many tasks.",
               "why_relevant": "It sits on the same line as the instruction-tuning and chain-of-thought papers you saved lately: getting a large model to understand a task.",
               "caution": "Few-shot results are unstable; the paper itself discusses limits and risks."}},
    "2010.11929": {
        "zh": {"one_liner": "把图像切成小块当词输入纯 Transformer，大数据预训练后可以追平卷积网络。",
               "why_relevant": "你收藏的 Swin、DeiT 都从这篇出发，把 Transformer 搬到视觉上。",
               "caution": "数据量不够时不如卷积网络；强结果依赖很大的预训练集。"},
        "en": {"one_liner": "Feeds image patches as words into a plain Transformer; pre-trained on large data it catches up with convolutional networks.",
               "why_relevant": "Swin and DeiT, both saved by you, start from this paper's idea of moving Transformers to vision.",
               "caution": "With little data it trails convolutional networks; the strong results need a very large pretraining set."}},
    "1906.08237": {
        "zh": {"one_liner": "用所有词序排列的似然来预训练，不遮盖词也能学到双向上下文。",
               "why_relevant": "属于预训练语言模型方向，和 BERT 的遮盖词思路形成对照。",
               "caution": "训练复杂，之后的简化方法（如 RoBERTa）往往更常用。"},
        "en": {"one_liner": "Pretrains on the likelihood over word-order permutations, learning bidirectional context without masking.",
               "why_relevant": "A pretrained-language-model paper that contrasts with BERT's masking idea.",
               "caution": "Training is complex, and simpler follow-ups such as RoBERTa are more commonly used."}},
    "1909.11942": {
        "zh": {"one_liner": "跨层共享参数、拆分词嵌入，让 BERT 更小更快。",
               "why_relevant": "关注模型效率的收藏里，它是预训练语言模型方向的代表。",
               "caution": "参数少不等于计算少，推理速度提升有限。"},
        "en": {"one_liner": "Shares parameters across layers and factorizes embeddings to make BERT smaller and quicker to train.",
               "why_relevant": "Among your efficiency-minded saves, it is the representative of the pretrained-language-model direction.",
               "caution": "Fewer parameters is not less compute; the inference speedup is limited."}},
    "1910.13461": {
        "zh": {"one_liner": "把文本打乱再还原的编码器-解码器预训练，生成和理解两头都强。",
               "why_relevant": "补足了你收藏的 BERT 系论文缺少的生成能力。",
               "caution": "加噪方式的选择对结果影响大，需要看消融实验。"},
        "en": {"one_liner": "An encoder-decoder pretrained by corrupting text and reconstructing it, strong at both generation and understanding.",
               "why_relevant": "It adds the generation side that the BERT-family papers you saved lack.",
               "caution": "The choice of noising scheme matters a lot; check the ablations."}},
    "1910.10683": {
        "zh": {"one_liner": "把所有任务都变成“文本到文本”，系统比较了预训练目标、结构和规模。",
               "why_relevant": "它的比较实验是你收藏的预训练论文里最全面的一篇。",
               "caution": "结论建立在它自己清洗的网页语料上，换数据未必成立。"},
        "en": {"one_liner": "Casts every task as text to text and systematically compares pretraining objectives, architectures and scale.",
               "why_relevant": "Its comparisons are the most thorough among the pretraining papers you saved.",
               "caution": "The conclusions rest on its own cleaned web corpus and may not hold for other data."}},
    "2003.10555": {
        "zh": {"one_liner": "不遮盖词，而是判断每个词是否被替换，同样算力下学得更多。",
               "why_relevant": "和 ALBERT 一样在讲预训练怎么更省，同属一个方向。",
               "caution": "主要在理解任务上验证，生成任务的结论较少。"},
        "en": {"one_liner": "Instead of masking, it detects which tokens were replaced, learning more from the same compute.",
               "why_relevant": "Like ALBERT it is about making pretraining cheaper, in the same direction.",
               "caution": "Validated mainly on understanding tasks; little evidence for generation."}},
    "1907.11692": {
        "zh": {"one_liner": "重新调参训练 BERT，发现它训练不足，多训几步就超过后继模型。",
               "why_relevant": "你收藏并标为“已读懂”的一篇，是预训练方向的入口。",
               "caution": "收益来自更多数据和算力，不是新方法。"},
        "en": {"one_liner": "Retrains BERT with better settings and finds it was undertrained; more training beats its successors.",
               "why_relevant": "One you saved and marked as understood; an entry point to the pretraining direction.",
               "caution": "The gain comes from more data and compute, not a new method."}},
    "2203.15556": {
        "zh": {"one_liner": "固定算力下，模型大小与训练词数应同比例增长；小模型多训数据反而更好。",
               "why_relevant": "它修正了 Scaling Laws 一文的配比，是你收藏里讲规模最关键的一篇。",
               "caution": "结论针对密集 Transformer，其他结构要另测。"},
        "en": {"one_liner": "For a fixed compute budget, model size and training tokens should grow together; a smaller model on more data wins.",
               "why_relevant": "It corrects the split in the Scaling Laws paper and is the key scale paper in your saves.",
               "caution": "The conclusion is for dense Transformers; other designs need their own test."}},
    "2103.14030": {
        "zh": {"one_liner": "在可移位的局部窗口里做注意力，并逐层合并，成本随图像大小线性增长。",
               "why_relevant": "你收藏并标为“已读懂”的视觉 Transformer，被许多后续工作当作骨干。",
               "caution": "窗口设计较复杂，依赖具体任务的实现细节。"},
        "en": {"one_liner": "Does attention inside shifted local windows and merges patches layer by layer, so cost grows linearly with image size.",
               "why_relevant": "A vision Transformer you saved and marked as understood; many later works use it as a backbone.",
               "caution": "The window design is intricate and depends on implementation details per task."}},
    "2012.12877": {
        "zh": {"one_liner": "更好的训练配方加蒸馏标记，让视觉 Transformer 只靠 ImageNet 就能训好。",
               "why_relevant": "回答了 ViT 需要海量数据的疑问，与你收藏的 Swin 互补。",
               "caution": "依赖卷积网络做教师，不是纯粹的 Transformer 路线。"},
        "en": {"one_liner": "A better recipe plus a distillation token lets a Vision Transformer train on ImageNet alone.",
               "why_relevant": "It answers the question of ViT's data hunger and complements the Swin paper you saved.",
               "caution": "It relies on a convolutional teacher, so it is not a pure Transformer route."}},
    "2103.00020": {
        "zh": {"one_liner": "让图像和文字描述在同一空间里对齐，不用训练就能给图片分类。",
               "why_relevant": "把视觉模型和语言监督连起来，连接了你收藏的两个方向。",
               "caution": "零样本分类在细分类别上较弱，数据来自网络，有偏见风险。"},
        "en": {"one_liner": "Aligns images and text captions in one space so images can be classified with no extra training.",
               "why_relevant": "It links vision models to language supervision and so bridges two directions you saved.",
               "caution": "Zero-shot classification is weak on fine-grained classes, and web data brings bias risks."}},
    "2111.06377": {
        "zh": {"one_liner": "遮住大部分图像块再还原，让大型视觉 Transformer 只用图片也能预训练。",
               "why_relevant": "是 BERT 的遮盖思路在视觉上的对应，连接了你收藏的两个方向。",
               "caution": "主要验证了分类和迁移，生成式用途不是重点。"},
        "en": {"one_liner": "Hides most image patches and reconstructs them, so large Vision Transformers can be pretrained on images alone.",
               "why_relevant": "The vision counterpart of BERT's masking idea, tying two directions you saved together.",
               "caution": "Validated mostly on classification and transfer; generative use is not the focus."}},
    "2105.01601": {
        "zh": {"one_liner": "用多层感知机代替卷积和注意力，在图像块和通道之间混合信息。",
               "why_relevant": "这篇你标了“不相关”：它不用注意力，偏离了你关注的主线。",
               "caution": "没有注意力，不能代表 Transformer 路线的结论。"},
        "en": {"one_liner": "Replaces convolution and attention with MLPs that mix information across patches and channels.",
               "why_relevant": "You marked this one not relevant: it uses no attention, away from your main line.",
               "caution": "With no attention it says little about the Transformer route."}},
    "2005.12872": {
        "zh": {"one_liner": "把目标检测当成集合预测，用 Transformer 直接输出结果，去掉锚框等手工设计。",
               "why_relevant": "这篇你标了“不相关”：它是检测任务，不在你关注的语言与注意力主线上。",
               "caution": "训练收敛慢，小目标表现较弱。"},
        "en": {"one_liner": "Treats object detection as set prediction and outputs results directly from a Transformer, dropping anchors and similar hand design.",
               "why_relevant": "You marked this one not relevant: it is about detection, off your language-and-attention line.",
               "caution": "Training converges slowly and small objects are weak."}},
    "2004.05150": {
        "zh": {"one_liner": "滑动窗口加少量全局词，让注意力成本随文档长度线性增长，能处理几千词。",
               "why_relevant": "你最近开始收藏高效注意力方向，这篇是长文档的入口。",
               "caution": "窗口大小和全局词要按任务调，没有通用设置。"},
        "en": {"one_liner": "A sliding window plus a few global tokens makes attention cost linear in document length, handling thousands of tokens.",
               "why_relevant": "You have started saving efficient-attention papers, and this is the entry point for long documents.",
               "caution": "Window size and global tokens must be tuned per task; there is no universal setting."}},
    "2001.04451": {
        "zh": {"one_liner": "用哈希找相似的键、用可逆层省显存，让长序列 Transformer 更省。",
               "why_relevant": "高效注意力方向里省显存思路最特别的一篇。",
               "caution": "哈希带来近似误差，短序列上反而不划算。"},
        "en": {"one_liner": "Uses hashing to find similar keys and reversible layers to save memory, making long-sequence Transformers cheaper.",
               "why_relevant": "The most unusual memory-saving idea in the efficient-attention direction.",
               "caution": "Hashing adds approximation error and does not pay off on short sequences."}},
    "2006.04768": {
        "zh": {"one_liner": "注意力矩阵近似低秩，把键和值投影到更短长度，成本线性。",
               "why_relevant": "与 Longformer、Reformer 一起构成你收藏的高效注意力三条路线。",
               "caution": "低秩假设并非对所有任务成立。"},
        "en": {"one_liner": "The attention matrix is nearly low rank, so projecting keys and values to a shorter length gives linear cost.",
               "why_relevant": "With Longformer and Reformer it forms the three routes to efficient attention you saved.",
               "caution": "The low-rank assumption does not hold for every task."}},
    "2009.14794": {
        "zh": {"one_liner": "用随机特征近似 softmax 注意力，有理论保证，成本随长度线性。",
               "why_relevant": "高效注意力方向里理论最完整的一篇。",
               "caution": "你标了“太难”：推导依赖随机特征的数学，建议先读 Linformer。"},
        "en": {"one_liner": "Approximates softmax attention with random features, with theoretical guarantees and cost linear in length.",
               "why_relevant": "The most theoretically complete paper in the efficient-attention direction.",
               "caution": "You marked it too hard: the derivation needs random-feature maths; read Linformer first."}},
    "2205.14135": {
        "zh": {"one_liner": "分块计算精确注意力，减少对显存的读写，更快也更省。",
               "why_relevant": "与前面的近似方法不同，它不改结果，是高效注意力方向的实用收尾。",
               "caution": "收益取决于 GPU 的内存层次，换硬件要重测。"},
        "en": {"one_liner": "Computes exact attention in tiles to cut reads and writes to slow memory, faster and leaner.",
               "why_relevant": "Unlike the approximate methods before it, it changes no result, a practical close to the efficient-attention direction.",
               "caution": "The gain depends on the GPU memory hierarchy; re-measure on other hardware."}},
    "2104.09864": {
        "zh": {"one_liner": "用旋转向量编码位置，让注意力分数只依赖相对距离，长度更灵活。",
               "why_relevant": "长上下文模型普遍采用它，补上了高效注意力里位置编码这一环。",
               "caution": "外推到比训练更长的序列时仍会退化。"},
        "en": {"one_liner": "Encodes position by rotating query and key vectors so attention scores depend on relative distance.",
               "why_relevant": "Long-context models widely adopt it, filling in the position-encoding piece of efficient attention.",
               "caution": "It still degrades when extrapolating beyond the training length."}},
    "2109.01652": {
        "zh": {"one_liner": "用大量“指令形式”的任务微调语言模型，没见过的任务也能零样本完成。",
               "why_relevant": "你本周新开的对齐与指令微调方向的起点。",
               "caution": "收益随任务数量和模型规模增长，小模型不明显。"},
        "en": {"one_liner": "Fine-tunes a language model on many tasks phrased as instructions so unseen tasks work zero-shot.",
               "why_relevant": "The starting point of the alignment and instruction-tuning direction you began this week.",
               "caution": "The gain grows with task count and model size and is small for small models."}},
    "2201.11903": {
        "zh": {"one_liner": "提示里给出带推理步骤的例子，大模型就会自己写步骤，推理题准确率大增。",
               "why_relevant": "说明提示本身也能改变模型行为，与指令微调互为补充。",
               "caution": "只在足够大的模型上有效，写出的步骤不一定忠实于真实推理。"},
        "en": {"one_liner": "Examples with reasoning steps in the prompt make a large model write its own steps and greatly raise reasoning accuracy.",
               "why_relevant": "It shows prompts alone can change model behaviour, complementing instruction tuning.",
               "caution": "Works only on large enough models, and the written steps may not reflect its actual reasoning."}},
    "2203.02155": {
        "zh": {"one_liner": "先用人工示范微调，再用人类偏好排序做强化学习，小模型的回答比大模型更受欢迎。",
               "why_relevant": "你对齐方向的核心论文，后面的 Constitutional AI、DPO 都在改它的流程。",
               "caution": "评价来自特定标注者，不代表所有用户的偏好。"},
        "en": {"one_liner": "Fine-tunes on human demonstrations then runs reinforcement learning on human preference rankings; a smaller model's answers are preferred over a larger one's.",
               "why_relevant": "The core paper of your alignment direction; Constitutional AI and DPO both rework its pipeline.",
               "caution": "The judgments come from particular annotators and do not represent every user."}},
    "2212.08073": {
        "zh": {"one_liner": "用一份成文原则让模型自我批评、自我修改，再用 AI 比较训练偏好模型。",
               "why_relevant": "接在 InstructGPT 之后，讲怎样少用人工标注。",
               "caution": "原则由作者选定，结果取决于这份原则本身。"},
        "en": {"one_liner": "Uses a short written constitution so the model critiques and revises itself, then trains a preference model from AI comparisons.",
               "why_relevant": "It follows InstructGPT and asks how to use fewer human labels.",
               "caution": "The principles are chosen by the authors, so results depend on that list."}},
    "2305.18290": {
        "zh": {"one_liner": "不再单独训练奖励模型，直接用分类式损失优化偏好对，更稳、更省。",
               "why_relevant": "你对齐方向里最新的一篇，把 InstructGPT 的两阶段流程合成一步。",
               "caution": "你标了“太难”：推导需要先熟悉 RLHF 的目标函数。"},
        "en": {"one_liner": "Skips the separate reward model and optimizes preference pairs directly with a classification-style loss, more stable and cheaper.",
               "why_relevant": "The newest in your alignment direction, collapsing InstructGPT's two stages into one.",
               "caution": "You marked it too hard: the derivation assumes the RLHF objective is familiar."}},
}


def _digest():
    payload = {"name": NAME, "keywords": KEYWORDS, "pins": PIN_HISTORY, "directions": DIRECTIONS, "papers": PAPERS,
               "previews": PREVIEWS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


DIGEST = _digest()


def key_of(paper):
    """The key the real code gives an arXiv paper: the DataCite DOI of its identifier."""
    return "https://doi.org/10.48550/arxiv." + paper["arxiv_id"]


def candidates():
    return [p for p in PAPERS if p["role"] == "candidate"]


def history():
    return [p for p in PAPERS if p["role"] != "candidate"]

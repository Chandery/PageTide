"""The built-in data of the demo project (the onboarding tour). Pure data: nothing here reads a file, the network or a clock.

Provenance (read this before trusting any text below):
  * Identifiers, titles, first-version dates and the `abstract` of every paper are public arXiv metadata (CC0),
    checked against export.arxiv.org on 2026-10-24: the abstracts are verbatim (whitespace collapsed).
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
ABSTRACTS_VERIFIED = True   # see the header: verbatim arXiv abstracts, checked 2026-10-24

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
       'The dominant sequence transduction models are based on complex recurrent or convolutional neural networks in '
       'an encoder-decoder configuration. The best performing models also connect the encoder and decoder through an '
       'attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention '
       'mechanisms, dispensing with recurrence and convolutions entirely. Experiments on two machine translation tasks'
       ' show these models to be superior in quality while being more parallelizable and requiring significantly less '
       'time to train. Our model achieves 28.4 BLEU on the WMT 2014 English-to-German translation task, improving over'
       ' the existing best results, including ensembles by over 2 BLEU. On the WMT 2014 English-to-French translation '
       'task, our model establishes a new single-model state-of-the-art BLEU score of 41.8 after training for 3.5 days'
       ' on eight GPUs, a small fraction of the training costs of the best models from the literature. We show that '
       'the Transformer generalizes well to other tasks by applying it successfully to English constituency parsing '
       'both with large and limited training data.', "candidate"),
    _p("1810.04805", "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding", "2018-10-11",
       ["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee"],
       'We introduce a new language representation model called BERT, which stands for Bidirectional Encoder '
       'Representations from Transformers. Unlike recent language representation models, BERT is designed to pre-train'
       ' deep bidirectional representations from unlabeled text by jointly conditioning on both left and right context'
       ' in all layers. As a result, the pre-trained BERT model can be fine-tuned with just one additional output '
       'layer to create state-of-the-art models for a wide range of tasks, such as question answering and language '
       'inference, without substantial task-specific architecture modifications. BERT is conceptually simple and '
       'empirically powerful. It obtains new state-of-the-art results on eleven natural language processing tasks, '
       'including pushing the GLUE score to 80.5% (7.7% point absolute improvement), MultiNLI accuracy to 86.7% (4.6% '
       'absolute improvement), SQuAD v1.1 question answering Test F1 to 93.2 (1.5 point absolute improvement) and '
       'SQuAD v2.0 Test F1 to 83.1 (5.1 point absolute improvement).', "candidate"),
    _p("2001.08361", "Scaling Laws for Neural Language Models", "2020-01-23", ["Jared Kaplan", "Sam McCandlish", "Tom Henighan"],
       'We study empirical scaling laws for language model performance on the cross-entropy loss. The loss scales as a'
       ' power-law with model size, dataset size, and the amount of compute used for training, with some trends '
       'spanning more than seven orders of magnitude. Other architectural details such as network width or depth have '
       'minimal effects within a wide range. Simple equations govern the dependence of overfitting on model/dataset '
       'size and the dependence of training speed on model size. These relationships allow us to determine the optimal'
       ' allocation of a fixed compute budget. Larger models are significantly more sample-efficient, such that '
       'optimally compute-efficient training involves training very large models on a relatively modest amount of data'
       ' and stopping significantly before convergence.', "candidate"),
    _p("2005.14165", "Language Models are Few-Shot Learners", "2020-05-28", ["Tom B. Brown", "Benjamin Mann", "Nick Ryder"],
       'Recent work has demonstrated substantial gains on many NLP tasks and benchmarks by pre-training on a large '
       'corpus of text followed by fine-tuning on a specific task. While typically task-agnostic in architecture, this'
       ' method still requires task-specific fine-tuning datasets of thousands or tens of thousands of examples. By '
       'contrast, humans can generally perform a new language task from only a few examples or from simple '
       'instructions - something which current NLP systems still largely struggle to do. Here we show that scaling up '
       'language models greatly improves task-agnostic, few-shot performance, sometimes even reaching competitiveness '
       'with prior state-of-the-art fine-tuning approaches. Specifically, we train GPT-3, an autoregressive language '
       'model with 175 billion parameters, 10x more than any previous non-sparse language model, and test its '
       'performance in the few-shot setting. For all tasks, GPT-3 is applied without any gradient updates or '
       'fine-tuning, with tasks and few-shot demonstrations specified purely via text interaction with the model. '
       'GPT-3 achieves strong performance on many NLP datasets, including translation, question-answering, and cloze '
       'tasks, as well as several tasks that require on-the-fly reasoning or domain adaptation, such as unscrambling '
       'words, using a novel word in a sentence, or performing 3-digit arithmetic. At the same time, we also identify '
       "some datasets where GPT-3's few-shot learning still struggles, as well as some datasets where GPT-3 faces "
       'methodological issues related to training on large web corpora. Finally, we find that GPT-3 can generate '
       'samples of news articles which human evaluators have difficulty distinguishing from articles written by '
       'humans. We discuss broader societal impacts of this finding and of GPT-3 in general.', "candidate"),
    _p("2010.11929", "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale", "2020-10-22",
       ["Alexey Dosovitskiy", "Lucas Beyer", "Alexander Kolesnikov"],
       'While the Transformer architecture has become the de-facto standard for natural language processing tasks, its'
       ' applications to computer vision remain limited. In vision, attention is either applied in conjunction with '
       'convolutional networks, or used to replace certain components of convolutional networks while keeping their '
       'overall structure in place. We show that this reliance on CNNs is not necessary and a pure transformer applied'
       ' directly to sequences of image patches can perform very well on image classification tasks. When pre-trained '
       'on large amounts of data and transferred to multiple mid-sized or small image recognition benchmarks '
       '(ImageNet, CIFAR-100, VTAB, etc.), Vision Transformer (ViT) attains excellent results compared to '
       'state-of-the-art convolutional networks while requiring substantially fewer computational resources to train.', "candidate"),
    # ---- pretrained language models --------------------------------------------------------------------------
    _p("1906.08237", "XLNet: Generalized Autoregressive Pretraining for Language Understanding", "2019-06-19",
       ["Zhilin Yang", "Zihang Dai", "Yiming Yang"],
       'With the capability of modeling bidirectional contexts, denoising autoencoding based pretraining like BERT '
       'achieves better performance than pretraining approaches based on autoregressive language modeling. However, '
       'relying on corrupting the input with masks, BERT neglects dependency between the masked positions and suffers '
       'from a pretrain-finetune discrepancy. In light of these pros and cons, we propose XLNet, a generalized '
       'autoregressive pretraining method that (1) enables learning bidirectional contexts by maximizing the expected '
       'likelihood over all permutations of the factorization order and (2) overcomes the limitations of BERT thanks '
       'to its autoregressive formulation. Furthermore, XLNet integrates ideas from Transformer-XL, the '
       'state-of-the-art autoregressive model, into pretraining. Empirically, under comparable experiment settings, '
       'XLNet outperforms BERT on 20 tasks, often by a large margin, including question answering, natural language '
       'inference, sentiment analysis, and document ranking.', "useful", "lm", 26.4),
    _p("1909.11942", "ALBERT: A Lite BERT for Self-supervised Learning of Language Representations", "2019-09-26",
       ["Zhenzhong Lan", "Mingda Chen", "Sebastian Goodman"],
       'Increasing model size when pretraining natural language representations often results in improved performance '
       'on downstream tasks. However, at some point further model increases become harder due to GPU/TPU memory '
       'limitations and longer training times. To address these problems, we present two parameter-reduction '
       'techniques to lower memory consumption and increase the training speed of BERT. Comprehensive empirical '
       'evidence shows that our proposed methods lead to models that scale much better compared to the original BERT. '
       'We also use a self-supervised loss that focuses on modeling inter-sentence coherence, and show it consistently'
       ' helps downstream tasks with multi-sentence inputs. As a result, our best model establishes new '
       'state-of-the-art results on the GLUE, RACE, and \\squad benchmarks while having fewer parameters compared to '
       'BERT-large. The code and the pretrained models are available at https://github.com/google-research/ALBERT.', "useful", "lm", 25.2),
    _p("1910.13461", "BART: Denoising Sequence-to-Sequence Pre-training for Natural Language Generation, Translation, and Comprehension",
       "2019-10-29", ["Mike Lewis", "Yinhan Liu", "Naman Goyal"],
       'We present BART, a denoising autoencoder for pretraining sequence-to-sequence models. BART is trained by (1) '
       'corrupting text with an arbitrary noising function, and (2) learning a model to reconstruct the original text.'
       ' It uses a standard Tranformer-based neural machine translation architecture which, despite its simplicity, '
       'can be seen as generalizing BERT (due to the bidirectional encoder), GPT (with the left-to-right decoder), and'
       ' many other more recent pretraining schemes. We evaluate a number of noising approaches, finding the best '
       'performance by both randomly shuffling the order of the original sentences and using a novel in-filling '
       'scheme, where spans of text are replaced with a single mask token. BART is particularly effective when fine '
       'tuned for text generation but also works well for comprehension tasks. It matches the performance of RoBERTa '
       'with comparable training resources on GLUE and SQuAD, achieves new state-of-the-art results on a range of '
       'abstractive dialogue, question answering, and summarization tasks, with gains of up to 6 ROUGE. BART also '
       'provides a 1.1 BLEU increase over a back-translation system for machine translation, with only target language'
       ' pretraining. We also report ablation experiments that replicate other pretraining schemes within the BART '
       'framework, to better measure which factors most influence end-task performance.', "useful", "lm", 24.1),
    _p("1910.10683", "Exploring the Limits of Transfer Learning with a Unified Text-to-Text Transformer", "2019-10-23",
       ["Colin Raffel", "Noam Shazeer", "Adam Roberts"],
       'Transfer learning, where a model is first pre-trained on a data-rich task before being fine-tuned on a '
       'downstream task, has emerged as a powerful technique in natural language processing (NLP). The effectiveness '
       'of transfer learning has given rise to a diversity of approaches, methodology, and practice. In this paper, we'
       ' explore the landscape of transfer learning techniques for NLP by introducing a unified framework that '
       'converts all text-based language problems into a text-to-text format. Our systematic study compares '
       'pre-training objectives, architectures, unlabeled data sets, transfer approaches, and other factors on dozens '
       'of language understanding tasks. By combining the insights from our exploration with scale and our new '
       "``Colossal Clean Crawled Corpus'', we achieve state-of-the-art results on many benchmarks covering "
       'summarization, question answering, text classification, and more. To facilitate future work on transfer '
       'learning for NLP, we release our data set, pre-trained models, and code.', "useful", "lm", 22.7,
       marks=[("understood", 8.0)]),
    _p("2003.10555", "ELECTRA: Pre-training Text Encoders as Discriminators Rather Than Generators", "2020-03-23",
       ["Kevin Clark", "Minh-Thang Luong", "Quoc V. Le"],
       'Masked language modeling (MLM) pre-training methods such as BERT corrupt the input by replacing some tokens '
       'with [MASK] and then train a model to reconstruct the original tokens. While they produce good results when '
       'transferred to downstream NLP tasks, they generally require large amounts of compute to be effective. As an '
       'alternative, we propose a more sample-efficient pre-training task called replaced token detection. Instead of '
       'masking the input, our approach corrupts it by replacing some tokens with plausible alternatives sampled from '
       'a small generator network. Then, instead of training a model that predicts the original identities of the '
       'corrupted tokens, we train a discriminative model that predicts whether each token in the corrupted input was '
       'replaced by a generator sample or not. Thorough experiments demonstrate this new pre-training task is more '
       'efficient than MLM because the task is defined over all input tokens rather than just the small subset that '
       'was masked out. As a result, the contextual representations learned by our approach substantially outperform '
       'the ones learned by BERT given the same model size, data, and compute. The gains are particularly strong for '
       'small models; for example, we train a model on one GPU for 4 days that outperforms GPT (trained using 30x more'
       ' compute) on the GLUE natural language understanding benchmark. Our approach also works well at scale, where '
       'it performs comparably to RoBERTa and XLNet while using less than 1/4 of their compute and outperforms them '
       'when using the same amount of compute.', "useful", "lm", 21.3),
    _p("1907.11692", "RoBERTa: A Robustly Optimized BERT Pretraining Approach", "2019-07-26",
       ["Yinhan Liu", "Myle Ott", "Naman Goyal"],
       'Language model pretraining has led to significant performance gains but careful comparison between different '
       'approaches is challenging. Training is computationally expensive, often done on private datasets of different '
       'sizes, and, as we will show, hyperparameter choices have significant impact on the final results. We present a'
       ' replication study of BERT pretraining (Devlin et al., 2019) that carefully measures the impact of many key '
       'hyperparameters and training data size. We find that BERT was significantly undertrained, and can match or '
       'exceed the performance of every model published after it. Our best model achieves state-of-the-art results on '
       'GLUE, RACE and SQuAD. These results highlight the importance of previously overlooked design choices, and '
       'raise questions about the source of recently reported improvements. We release our models and code.', "useful", "lm", 18.9, marks=[("understood", 1.8)]),
    _p("2203.15556", "Training Compute-Optimal Large Language Models", "2022-03-29",
       ["Jordan Hoffmann", "Sebastian Borgeaud", "Arthur Mensch"],
       'We investigate the optimal model size and number of tokens for training a transformer language model under a '
       'given compute budget. We find that current large language models are significantly undertrained, a consequence'
       ' of the recent focus on scaling language models whilst keeping the amount of training data constant. By '
       'training over 400 language models ranging from 70 million to over 16 billion parameters on 5 to 500 billion '
       'tokens, we find that for compute-optimal training, the model size and the number of training tokens should be '
       'scaled equally: for every doubling of model size the number of training tokens should also be doubled. We test'
       ' this hypothesis by training a predicted compute-optimal model, Chinchilla, that uses the same compute budget '
       'as Gopher but with 70B parameters and 4$\\times$ more more data. Chinchilla uniformly and significantly '
       'outperforms Gopher (280B), GPT-3 (175B), Jurassic-1 (178B), and Megatron-Turing NLG (530B) on a large range of'
       ' downstream evaluation tasks. This also means that Chinchilla uses substantially less compute for fine-tuning '
       'and inference, greatly facilitating downstream usage. As a highlight, Chinchilla reaches a state-of-the-art '
       'average accuracy of 67.5% on the MMLU benchmark, greater than a 7% improvement over Gopher.', "useful", "lm", 17.4),
    # ---- vision Transformers -----------------------------------------------------------------------------------
    _p("2103.14030", "Swin Transformer: Hierarchical Vision Transformer using Shifted Windows", "2021-03-25",
       ["Ze Liu", "Yutong Lin", "Yue Cao"],
       'This paper presents a new vision Transformer, called Swin Transformer, that capably serves as a '
       'general-purpose backbone for computer vision. Challenges in adapting Transformer from language to vision arise'
       ' from differences between the two domains, such as large variations in the scale of visual entities and the '
       'high resolution of pixels in images compared to words in text. To address these differences, we propose a '
       'hierarchical Transformer whose representation is computed with \\textbf{S}hifted \\textbf{win}dows. The shifted '
       'windowing scheme brings greater efficiency by limiting self-attention computation to non-overlapping local '
       'windows while also allowing for cross-window connection. This hierarchical architecture has the flexibility to'
       ' model at various scales and has linear computational complexity with respect to image size. These qualities '
       'of Swin Transformer make it compatible with a broad range of vision tasks, including image classification '
       '(87.3 top-1 accuracy on ImageNet-1K) and dense prediction tasks such as object detection (58.7 box AP and 51.1'
       ' mask AP on COCO test-dev) and semantic segmentation (53.5 mIoU on ADE20K val). Its performance surpasses the '
       'previous state-of-the-art by a large margin of +2.7 box AP and +2.6 mask AP on COCO, and +3.2 mIoU on ADE20K, '
       'demonstrating the potential of Transformer-based models as vision backbones. The hierarchical design and the '
       'shifted window approach also prove beneficial for all-MLP architectures. The code and models are publicly '
       'available at~\\url{https://github.com/microsoft/Swin-Transformer}.', "useful", "vit", 16.8, marks=[("understood", 7.6)]),
    _p("2012.12877", "Training data-efficient image transformers & distillation through attention", "2020-12-23",
       ["Hugo Touvron", "Matthieu Cord", "Matthijs Douze"],
       'Recently, neural networks purely based on attention were shown to address image understanding tasks such as '
       'image classification. However, these visual transformers are pre-trained with hundreds of millions of images '
       'using an expensive infrastructure, thereby limiting their adoption. In this work, we produce a competitive '
       'convolution-free transformer by training on Imagenet only. We train them on a single computer in less than 3 '
       'days. Our reference vision transformer (86M parameters) achieves top-1 accuracy of 83.1% (single-crop '
       'evaluation) on ImageNet with no external data. More importantly, we introduce a teacher-student strategy '
       'specific to transformers. It relies on a distillation token ensuring that the student learns from the teacher '
       'through attention. We show the interest of this token-based distillation, especially when using a convnet as a'
       ' teacher. This leads us to report results competitive with convnets for both Imagenet (where we obtain up to '
       '85.2% accuracy) and when transferring to other tasks. We share our code and models.', "useful", "vit", 15.9),
    _p("2103.00020", "Learning Transferable Visual Models From Natural Language Supervision", "2021-02-26",
       ["Alec Radford", "Jong Wook Kim", "Chris Hallacy"],
       'State-of-the-art computer vision systems are trained to predict a fixed set of predetermined object '
       'categories. This restricted form of supervision limits their generality and usability since additional labeled'
       ' data is needed to specify any other visual concept. Learning directly from raw text about images is a '
       'promising alternative which leverages a much broader source of supervision. We demonstrate that the simple '
       'pre-training task of predicting which caption goes with which image is an efficient and scalable way to learn '
       'SOTA image representations from scratch on a dataset of 400 million (image, text) pairs collected from the '
       'internet. After pre-training, natural language is used to reference learned visual concepts (or describe new '
       'ones) enabling zero-shot transfer of the model to downstream tasks. We study the performance of this approach '
       'by benchmarking on over 30 different existing computer vision datasets, spanning tasks such as OCR, action '
       'recognition in videos, geo-localization, and many types of fine-grained object classification. The model '
       'transfers non-trivially to most tasks and is often competitive with a fully supervised baseline without the '
       'need for any dataset specific training. For instance, we match the accuracy of the original ResNet-50 on '
       'ImageNet zero-shot without needing to use any of the 1.28 million training examples it was trained on. We '
       'release our code and pre-trained model weights at https://github.com/OpenAI/CLIP.', "useful", "vit", 3.0),
    _p("2111.06377", "Masked Autoencoders Are Scalable Vision Learners", "2021-11-11",
       ["Kaiming He", "Xinlei Chen", "Saining Xie"],
       'This paper shows that masked autoencoders (MAE) are scalable self-supervised learners for computer vision. Our'
       ' MAE approach is simple: we mask random patches of the input image and reconstruct the missing pixels. It is '
       'based on two core designs. First, we develop an asymmetric encoder-decoder architecture, with an encoder that '
       'operates only on the visible subset of patches (without mask tokens), along with a lightweight decoder that '
       'reconstructs the original image from the latent representation and mask tokens. Second, we find that masking a'
       ' high proportion of the input image, e.g., 75%, yields a nontrivial and meaningful self-supervisory task. '
       'Coupling these two designs enables us to train large models efficiently and effectively: we accelerate '
       'training (by 3x or more) and improve accuracy. Our scalable approach allows for learning high-capacity models '
       'that generalize well: e.g., a vanilla ViT-Huge model achieves the best accuracy (87.8%) among methods that use'
       ' only ImageNet-1K data. Transfer performance in downstream tasks outperforms supervised pre-training and shows'
       ' promising scaling behavior.', "useful", "vit", 11.8),
    _p("2105.01601", "MLP-Mixer: An all-MLP Architecture for Vision", "2021-05-04",
       ["Ilya Tolstikhin", "Neil Houlsby", "Alexander Kolesnikov"],
       'Convolutional Neural Networks (CNNs) are the go-to model for computer vision. Recently, attention-based '
       'networks, such as the Vision Transformer, have also become popular. In this paper we show that while '
       'convolutions and attention are both sufficient for good performance, neither of them are necessary. We present'
       ' MLP-Mixer, an architecture based exclusively on multi-layer perceptrons (MLPs). MLP-Mixer contains two types '
       'of layers: one with MLPs applied independently to image patches (i.e. "mixing" the per-location features), and'
       ' one with MLPs applied across patches (i.e. "mixing" spatial information). When trained on large datasets, or '
       'with modern regularization schemes, MLP-Mixer attains competitive scores on image classification benchmarks, '
       'with pre-training and inference cost comparable to state-of-the-art models. We hope that these results spark '
       'further research beyond the realms of well established CNNs and Transformers.', "irrelevant", "vit", 11.2),
    _p("2005.12872", "End-to-End Object Detection with Transformers", "2020-05-26", ["Nicolas Carion", "Francisco Massa", "Gabriel Synnaeve"],
       'We present a new method that views object detection as a direct set prediction problem. Our approach '
       'streamlines the detection pipeline, effectively removing the need for many hand-designed components like a '
       'non-maximum suppression procedure or anchor generation that explicitly encode our prior knowledge about the '
       'task. The main ingredients of the new framework, called DEtection TRansformer or DETR, are a set-based global '
       'loss that forces unique predictions via bipartite matching, and a transformer encoder-decoder architecture. '
       'Given a fixed small set of learned object queries, DETR reasons about the relations of the objects and the '
       'global image context to directly output the final set of predictions in parallel. The new model is '
       'conceptually simple and does not require a specialized library, unlike many other modern detectors. DETR '
       'demonstrates accuracy and run-time performance on par with the well-established and highly-optimized Faster '
       'RCNN baseline on the challenging COCO object detection dataset. Moreover, DETR can be easily generalized to '
       'produce panoptic segmentation in a unified manner. We show that it significantly outperforms competitive '
       'baselines. Training code and pretrained models are available at https://github.com/facebookresearch/detr.', "irrelevant", "vit", 10.4),
    # ---- efficient attention and long context -----------------------------------------------------------------
    _p("2004.05150", "Longformer: The Long-Document Transformer", "2020-04-10", ["Iz Beltagy", "Matthew E. Peters", "Arman Cohan"],
       'Transformer-based models are unable to process long sequences due to their self-attention operation, which '
       'scales quadratically with the sequence length. To address this limitation, we introduce the Longformer with an'
       ' attention mechanism that scales linearly with sequence length, making it easy to process documents of '
       "thousands of tokens or longer. Longformer's attention mechanism is a drop-in replacement for the standard "
       'self-attention and combines a local windowed attention with a task motivated global attention. Following prior'
       ' work on long-sequence transformers, we evaluate Longformer on character-level language modeling and achieve '
       'state-of-the-art results on text8 and enwik8. In contrast to most prior work, we also pretrain Longformer and '
       'finetune it on a variety of downstream tasks. Our pretrained Longformer consistently outperforms RoBERTa on '
       'long document tasks and sets new state-of-the-art results on WikiHop and TriviaQA. We finally introduce the '
       'Longformer-Encoder-Decoder (LED), a Longformer variant for supporting long document generative '
       'sequence-to-sequence tasks, and demonstrate its effectiveness on the arXiv summarization dataset.', "useful", "eff", 9.7),
    _p("2001.04451", "Reformer: The Efficient Transformer", "2020-01-13", ["Nikita Kitaev", "Lukasz Kaiser", "Anselm Levskaya"],
       'Large Transformer models routinely achieve state-of-the-art results on a number of tasks but training these '
       'models can be prohibitively costly, especially on long sequences. We introduce two techniques to improve the '
       'efficiency of Transformers. For one, we replace dot-product attention by one that uses locality-sensitive '
       'hashing, changing its complexity from O($L^2$) to O($L\\log L$), where $L$ is the length of the sequence. '
       'Furthermore, we use reversible residual layers instead of the standard residuals, which allows storing '
       'activations only once in the training process instead of $N$ times, where $N$ is the number of layers. The '
       'resulting model, the Reformer, performs on par with Transformer models while being much more memory-efficient '
       'and much faster on long sequences.', "useful", "eff", 9.1),
    _p("2006.04768", "Linformer: Self-Attention with Linear Complexity", "2020-06-08", ["Sinong Wang", "Belinda Z. Li", "Madian Khabsa"],
       'Large transformer models have shown extraordinary success in achieving state-of-the-art results in many '
       'natural language processing applications. However, training and deploying these models can be prohibitively '
       'costly for long sequences, as the standard self-attention mechanism of the Transformer uses $O(n^2)$ time and '
       'space with respect to sequence length. In this paper, we demonstrate that the self-attention mechanism can be '
       'approximated by a low-rank matrix. We further exploit this finding to propose a new self-attention mechanism, '
       'which reduces the overall self-attention complexity from $O(n^2)$ to $O(n)$ in both time and space. The '
       'resulting linear transformer, the \\textit{Linformer}, performs on par with standard Transformer models, while '
       'being much more memory- and time-efficient.', "useful", "eff", 8.4),
    _p("2009.14794", "Rethinking Attention with Performers", "2020-09-30", ["Krzysztof Choromanski", "Valerii Likhosherstov", "David Dohan"],
       'We introduce Performers, Transformer architectures which can estimate regular (softmax) full-rank-attention '
       'Transformers with provable accuracy, but using only linear (as opposed to quadratic) space and time '
       'complexity, without relying on any priors such as sparsity or low-rankness. To approximate softmax '
       'attention-kernels, Performers use a novel Fast Attention Via positive Orthogonal Random features approach '
       '(FAVOR+), which may be of independent interest for scalable kernel methods. FAVOR+ can be also used to '
       'efficiently model kernelizable attention mechanisms beyond softmax. This representational power is crucial to '
       'accurately compare softmax with other kernels for the first time on large-scale tasks, beyond the reach of '
       'regular Transformers, and investigate optimal attention-kernels. Performers are linear architectures fully '
       'compatible with regular Transformers and with strong theoretical guarantees: unbiased or nearly-unbiased '
       'estimation of the attention matrix, uniform convergence and low estimation variance. We tested Performers on a'
       ' rich set of tasks stretching from pixel-prediction through text models to protein sequence modeling. We '
       'demonstrate competitive results with other examined efficient sparse and dense attention methods, showcasing '
       'effectiveness of the novel attention-learning paradigm leveraged by Performers.', "useful", "eff", 7.3, marks=[("too_hard", 3.8)]),
    _p("2205.14135", "FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness", "2022-05-27",
       ["Tri Dao", "Daniel Y. Fu", "Stefano Ermon"],
       'Transformers are slow and memory-hungry on long sequences, since the time and memory complexity of '
       'self-attention are quadratic in sequence length. Approximate attention methods have attempted to address this '
       'problem by trading off model quality to reduce the compute complexity, but often do not achieve wall-clock '
       'speedup. We argue that a missing principle is making attention algorithms IO-aware -- accounting for reads and'
       ' writes between levels of GPU memory. We propose FlashAttention, an IO-aware exact attention algorithm that '
       'uses tiling to reduce the number of memory reads/writes between GPU high bandwidth memory (HBM) and GPU '
       'on-chip SRAM. We analyze the IO complexity of FlashAttention, showing that it requires fewer HBM accesses than'
       ' standard attention, and is optimal for a range of SRAM sizes. We also extend FlashAttention to block-sparse '
       'attention, yielding an approximate attention algorithm that is faster than any existing approximate attention '
       'method. FlashAttention trains Transformers faster than existing baselines: 15% end-to-end wall-clock speedup '
       'on BERT-large (seq. length 512) compared to the MLPerf 1.1 training speed record, 3$\\times$ speedup on GPT-2 '
       '(seq. length 1K), and 2.4$\\times$ speedup on long-range arena (seq. length 1K-4K). FlashAttention and '
       'block-sparse FlashAttention enable longer context in Transformers, yielding higher quality models (0.7 better '
       'perplexity on GPT-2 and 6.4 points of lift on long-document classification) and entirely new capabilities: the'
       ' first Transformers to achieve better-than-chance performance on the Path-X challenge (seq. length 16K, 61.4% '
       'accuracy) and Path-256 (seq. length 64K, 63.1% accuracy).', "useful", "eff", 4.6),
    _p("2104.09864", "RoFormer: Enhanced Transformer with Rotary Position Embedding", "2021-04-20", ["Jianlin Su", "Yu Lu", "Shengfeng Pan"],
       'Position encoding recently has shown effective in the transformer architecture. It enables valuable '
       'supervision for dependency modeling between elements at different positions of the sequence. In this paper, we'
       ' first investigate various methods to integrate positional information into the learning process of '
       'transformer-based language models. Then, we propose a novel method named Rotary Position Embedding(RoPE) to '
       'effectively leverage the positional information. Specifically, the proposed RoPE encodes the absolute position'
       ' with a rotation matrix and meanwhile incorporates the explicit relative position dependency in self-attention'
       ' formulation. Notably, RoPE enables valuable properties, including the flexibility of sequence length, '
       'decaying inter-token dependency with increasing relative distances, and the capability of equipping the linear'
       ' self-attention with relative position encoding. Finally, we evaluate the enhanced transformer with rotary '
       'position embedding, also called RoFormer, on various long text classification benchmark datasets. Our '
       'experiments show that it consistently overcomes its alternatives. Furthermore, we provide a theoretical '
       'analysis to explain some experimental results. RoFormer is already integrated into Huggingface: '
       '\\url{https://huggingface.co/docs/transformers/model_doc/roformer}.', "useful", "eff", 4.1),
    # ---- alignment and instruction tuning ---------------------------------------------------------------------
    _p("2109.01652", "Finetuned Language Models Are Zero-Shot Learners", "2021-09-03", ["Jason Wei", "Maarten Bosma", "Vincent Y. Zhao"],
       'This paper explores a simple method for improving the zero-shot learning abilities of language models. We show'
       ' that instruction tuning -- finetuning language models on a collection of tasks described via instructions -- '
       'substantially improves zero-shot performance on unseen tasks. We take a 137B parameter pretrained language '
       'model and instruction-tune it on over 60 NLP tasks verbalized via natural language instruction templates. We '
       'evaluate this instruction-tuned model, which we call FLAN, on unseen task types. FLAN substantially improves '
       'the performance of its unmodified counterpart and surpasses zero-shot 175B GPT-3 on 20 of 25 tasks that we '
       'evaluate. FLAN even outperforms few-shot GPT-3 by a large margin on ANLI, RTE, BoolQ, AI2-ARC, OpenbookQA, and'
       ' StoryCloze. Ablation studies reveal that number of finetuning datasets, model scale, and natural language '
       'instructions are key to the success of instruction tuning.', "useful", "align", 2.7),
    _p("2201.11903", "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models", "2022-01-28",
       ["Jason Wei", "Xuezhi Wang", "Dale Schuurmans"],
       'We explore how generating a chain of thought -- a series of intermediate reasoning steps -- significantly '
       'improves the ability of large language models to perform complex reasoning. In particular, we show how such '
       'reasoning abilities emerge naturally in sufficiently large language models via a simple method called chain of'
       ' thought prompting, where a few chain of thought demonstrations are provided as exemplars in prompting. '
       'Experiments on three large language models show that chain of thought prompting improves performance on a '
       'range of arithmetic, commonsense, and symbolic reasoning tasks. The empirical gains can be striking. For '
       'instance, prompting a 540B-parameter language model with just eight chain of thought exemplars achieves state '
       'of the art accuracy on the GSM8K benchmark of math word problems, surpassing even finetuned GPT-3 with a '
       'verifier.', "useful", "align", 2.1),
    _p("2203.02155", "Training language models to follow instructions with human feedback", "2022-03-04",
       ["Long Ouyang", "Jeff Wu", "Xu Jiang"],
       "Making language models bigger does not inherently make them better at following a user's intent. For example, "
       'large language models can generate outputs that are untruthful, toxic, or simply not helpful to the user. In '
       'other words, these models are not aligned with their users. In this paper, we show an avenue for aligning '
       'language models with user intent on a wide range of tasks by fine-tuning with human feedback. Starting with a '
       'set of labeler-written prompts and prompts submitted through the OpenAI API, we collect a dataset of labeler '
       'demonstrations of the desired model behavior, which we use to fine-tune GPT-3 using supervised learning. We '
       'then collect a dataset of rankings of model outputs, which we use to further fine-tune this supervised model '
       'using reinforcement learning from human feedback. We call the resulting models InstructGPT. In human '
       'evaluations on our prompt distribution, outputs from the 1.3B parameter InstructGPT model are preferred to '
       'outputs from the 175B GPT-3, despite having 100x fewer parameters. Moreover, InstructGPT models show '
       'improvements in truthfulness and reductions in toxic output generation while having minimal performance '
       'regressions on public NLP datasets. Even though InstructGPT still makes simple mistakes, our results show that'
       ' fine-tuning with human feedback is a promising direction for aligning language models with human intent.', "useful", "align", 3.3),
    _p("2212.08073", "Constitutional AI: Harmlessness from AI Feedback", "2022-12-15", ["Yuntao Bai", "Saurav Kadavath", "Sandipan Kundu"],
       'As AI systems become more capable, we would like to enlist their help to supervise other AIs. We experiment '
       'with methods for training a harmless AI assistant through self-improvement, without any human labels '
       'identifying harmful outputs. The only human oversight is provided through a list of rules or principles, and '
       "so we refer to the method as 'Constitutional AI'. The process involves both a supervised learning and a "
       'reinforcement learning phase. In the supervised phase we sample from an initial model, then generate '
       'self-critiques and revisions, and then finetune the original model on revised responses. In the RL phase, we '
       'sample from the finetuned model, use a model to evaluate which of the two samples is better, and then train a '
       'preference model from this dataset of AI preferences. We then train with RL using the preference model as the '
       "reward signal, i.e. we use 'RL from AI Feedback' (RLAIF). As a result we are able to train a harmless but "
       'non-evasive AI assistant that engages with harmful queries by explaining its objections to them. Both the SL '
       'and RL methods can leverage chain-of-thought style reasoning to improve the human-judged performance and '
       'transparency of AI decision making. These methods make it possible to control AI behavior more precisely and '
       'with far fewer human labels.', "useful", "align", 1.4),
    _p("2305.18290", "Direct Preference Optimization: Your Language Model is Secretly a Reward Model", "2023-05-29",
       ["Rafael Rafailov", "Archit Sharma", "Eric Mitchell"],
       'While large-scale unsupervised language models (LMs) learn broad world knowledge and some reasoning skills, '
       'achieving precise control of their behavior is difficult due to the completely unsupervised nature of their '
       'training. Existing methods for gaining such steerability collect human labels of the relative quality of model'
       ' generations and fine-tune the unsupervised LM to align with these preferences, often with reinforcement '
       'learning from human feedback (RLHF). However, RLHF is a complex and often unstable procedure, first fitting a '
       'reward model that reflects the human preferences, and then fine-tuning the large unsupervised LM using '
       'reinforcement learning to maximize this estimated reward without drifting too far from the original model. In '
       'this paper we introduce a new parameterization of the reward model in RLHF that enables extraction of the '
       'corresponding optimal policy in closed form, allowing us to solve the standard RLHF problem with only a simple'
       ' classification loss. The resulting algorithm, which we call Direct Preference Optimization (DPO), is stable, '
       'performant, and computationally lightweight, eliminating the need for sampling from the LM during fine-tuning '
       'or performing significant hyperparameter tuning. Our experiments show that DPO can fine-tune LMs to align with'
       ' human preferences as well as or better than existing methods. Notably, fine-tuning with DPO exceeds PPO-based'
       ' RLHF in ability to control sentiment of generations, and matches or improves response quality in '
       'summarization and single-turn dialogue while being substantially simpler to implement and train.', "useful", "align", 0.9,
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

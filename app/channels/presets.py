"""Discipline presets: which channels a new project starts with (ADR 0010).

A channel that needs a key or a login is listed in its preset but only searches once
the credential exists. Ids not yet implemented are skipped by the registry.
"""
DEFAULT = "cs_ai"

PRESETS = {
    "cs_ai": {"label": "计算机 / 人工智能",
              "channels": ["arxiv", "openalex", "crossref", "s2", "dblp", "openreview"],
              "optional": ["ieee", "springer", "scopus", "wos"]},
    "biomed": {"label": "生物医学",
               "channels": ["pubmed", "europepmc", "biorxiv", "medrxiv", "openalex", "crossref"],
               "optional": []},
    "physics_chem": {"label": "物理 / 化学 / 数学",
                     "channels": ["arxiv", "openalex", "crossref", "doaj"],
                     "optional": ["springer", "scopus", "wos"]},
    "econ_mgmt": {"label": "经济 / 管理",
                  "channels": ["openalex", "crossref", "osf", "core", "doaj", "cnki", "wanfang", "cssci"],
                  "optional": ["scopus", "wos"]},
    "humanities_social_cn": {"label": "人文社科（中文）",
                             "channels": ["cnki", "wanfang", "cqvip", "ncpssd", "cssci", "openalex",
                                          "crossref", "doaj", "hal", "osf"],
                             "optional": []},
    "education": {"label": "教育",
                  "channels": ["eric", "openalex", "crossref", "doaj", "osf", "cnki", "wanfang"],
                  "optional": []},
    "custom": {"label": "自定义", "channels": [], "optional": []},
}

# What every project that existed before migration 005 gets.
LEGACY_CHANNELS = ["arxiv", "openalex", "crossref"]


def preset(discipline):
    return PRESETS.get(discipline) or PRESETS[DEFAULT]


def channels_for(discipline):
    return list(preset(discipline)["channels"])


def valid(discipline):
    return discipline in PRESETS

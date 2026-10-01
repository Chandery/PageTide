"""Every channel, imported statically so PyInstaller bundles them (ADR 0010)."""
from .arxiv import ArXiv
from .crossref import Crossref
from .openalex import OpenAlexChannel

CHANNELS = [ArXiv(), OpenAlexChannel(), Crossref()]
_BY_ID = {channel.id: channel for channel in CHANNELS}


def get(channel_id):
    return _BY_ID.get(channel_id)


def all_channels():
    return list(CHANNELS)


def ids():
    return [channel.id for channel in CHANNELS]

"""Local preference values shared by recommendation consumers; no model calls."""
import datetime
import json
import math
from pathlib import Path


def read(data_dir):
    try:
        value=json.loads((Path(data_dir)/'settings.json').read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):
        return {}


def number(values,key,default,low,high,integer=False):
    value=values.get(key,default)
    if isinstance(value,bool):return default
    try:value=float(value)
    except (ValueError,TypeError):return default
    if not math.isfinite(value) or not low<=value<=high:return default
    return int(value) if integer else value


def count(data_dir):return number(read(data_dir),'recommendCount',5,1,20,True)


def sources(data_dir):
    values=read(data_dir)
    return values.get('sourceArxiv') is not False,values.get('sourceOpenAlex') is not False


def since(data_dir,today=None,default=None):
    today=today or datetime.date.today()
    value=read(data_dir).get('timePreference')
    if value=='all':return None
    days={'recent':7,'month':30}.get(value)
    return (today-datetime.timedelta(days=days)).isoformat() if days else default


def decay(data_dir):return number(read(data_dir),'decayWindow',30,7,365)
def boost(data_dir,default=0):return number(read(data_dir),'newPaperBoost',default,0,1)


# Hotspot mode (the default recommendation path): newest papers favoured by a weight, never cut off by age. The weight
# applies only while the owner has not chosen one; a time window applies only if the owner chose one.
HOTSPOT_BOOST=0.5


def route_beta(data_dir):
    """Learning-map mode is available only after the owner switches it on in Settings (beta, default off)."""
    return read(data_dir).get('routeBeta') is True


def validate(values):
    """Reject invalid visible preferences rather than storing a value the UI cannot consume."""
    if not isinstance(values,dict):raise ValueError('settings must be an object')
    for key,(low,high,integer) in {'recommendCount':(1,20,True),'decayWindow':(7,365,True),'newPaperBoost':(0,1,False)}.items():
        if key in values:
            v=values[key]
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not low<=v<=high or (integer and int(v)!=v):
                raise ValueError(f'{key} must be between {low} and {high}')
    for key in ('sourceArxiv','sourceOpenAlex','sourceBaiduScholar','baiduScholarConfirmed','routeBeta'):
        if key in values and not isinstance(values[key],bool):raise ValueError(f'{key} must be boolean')
    for key,allowed in {'theme':('light','dark','auto'),'language':('zh-CN','en-US'),'timePreference':('recent','month','all'),'updateFrequency':('daily','weekly','manual'),'apiProvider':('deepseek',)}.items():
        if key in values and values[key] not in allowed:raise ValueError(f'Invalid {key}')
    return dict(values)


def baidu_scholar(data_dir):
    """Baidu Scholar (Chinese keywords go to Baidu with the user's own key) is off until the user switches it on."""
    return read(data_dir).get('sourceBaiduScholar') is True


class SourcePolicy:
    """Which sources the user has switched on, and the one rule that says whether a paper may be shown or recommended."""

    def __init__(self,arxiv,general,baidu):
        self.arxiv,self.general,self.baidu=arxiv,general,baidu

    @staticmethod
    def is_arxiv(paper):
        return bool(paper.get('arxiv_id')) or 'arxiv' in str(paper.get('source') or '').casefold()

    @staticmethod
    def from_baidu(paper):
        """Whether Baidu Scholar reported the paper (its key form, or the sources listed in its open-access facts)."""
        from .source_adapters import paper_oa
        return str(paper.get('key') or '').startswith('baidu:') or 'baidu_scholar' in (paper_oa(paper).get('via') or [])

    def allows(self,paper):
        """arXiv papers follow the arXiv switch; a paper only Baidu reported follows the Baidu switch; one both OpenAlex and
        Baidu reported is allowed while either of its sources is on; the rest follow the journals-and-conferences switch."""
        if self.is_arxiv(paper):return self.arxiv
        if not self.from_baidu(paper):return self.general
        return bool(paper.get('openalex_id') and self.general) or self.baidu


def source_policy(data_dir):
    arxiv,general=sources(data_dir)
    return SourcePolicy(arxiv,general,baidu_scholar(data_dir))


def source_allowed(data_dir,paper):
    return source_policy(data_dir).allows(paper)

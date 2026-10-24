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
    for key in ('sourceArxiv','sourceOpenAlex','sourceBaiduScholar','sourceBaiduWeb','baiduScholarConfirmed','routeBeta','autoCheckUpdates'):
        if key in values and not isinstance(values[key],bool):raise ValueError(f'{key} must be boolean')
    for key,allowed in {'theme':('light','dark','auto'),'language':('zh-CN','en-US'),'timePreference':('recent','month','all'),'updateFrequency':('daily','weekly','manual'),'apiProvider':('deepseek',)}.items():
        if key in values and values[key] not in allowed:raise ValueError(f'Invalid {key}')
    return dict(values)


def baidu_scholar(data_dir):
    """Baidu Scholar (Chinese keywords go to Baidu with the user's own key) is off until the user switches it on."""
    return read(data_dir).get('sourceBaiduScholar') is True


def baidu_web(data_dir):
    """Baidu AI Search on xueshu.baidu.com (same data as Baidu Scholar, same Qianfan key) is off until the user switches it on."""
    return read(data_dir).get('sourceBaiduWeb') is True


def recency_filter(data_dir):
    """The search_recency_filter of the Baidu web search: only a time window the owner chose ("recent" = 7 days = week, "month");
    "all", no choice or anything else means no filter (recency is then a ranking weight, never a cut-off)."""
    return {'recent':'week','month':'month'}.get(read(data_dir).get('timePreference'))


class SourcePolicy:
    """Which sources the user has switched on, and the one rule that says whether a paper may be shown or recommended."""

    def __init__(self,arxiv,general,baidu,baidu_web=False):
        self.arxiv,self.general,self.baidu,self.baidu_web=arxiv,general,baidu,baidu_web

    @staticmethod
    def is_arxiv(paper):
        return bool(paper.get('arxiv_id')) or 'arxiv' in str(paper.get('source') or '').casefold()

    @staticmethod
    def baidu_reporters(paper):
        """Which Baidu sources reported the paper: the sources listed in its open-access facts (`via`); a `baidu:` key with none
        listed is the older Baidu Scholar form. Empty when Baidu did not report it."""
        from .source_adapters import paper_oa
        via=paper_oa(paper).get('via') or []
        found={name for name in ('baidu_scholar','baidu_web') if name in via}
        if not found and str(paper.get('key') or '').startswith('baidu:'):found={'baidu_scholar'}
        return found

    @staticmethod
    def from_baidu(paper):
        """Whether a Baidu source reported the paper."""
        return bool(SourcePolicy.baidu_reporters(paper))

    def allows(self,paper):
        """arXiv papers follow the arXiv switch; a paper only Baidu reported follows the switch of the Baidu source(s) that reported
        it (either, when both did); one both OpenAlex and Baidu reported is allowed while either of its sources is on; the rest
        follow the journals-and-conferences switch."""
        if self.is_arxiv(paper):return self.arxiv
        reporters=self.baidu_reporters(paper)
        if not reporters:return self.general
        return bool(paper.get('openalex_id') and self.general) or ('baidu_scholar' in reporters and self.baidu) or ('baidu_web' in reporters and self.baidu_web)


def source_policy(data_dir):
    arxiv,general=sources(data_dir)
    return SourcePolicy(arxiv,general,baidu_scholar(data_dir),baidu_web(data_dir))


def source_allowed(data_dir,paper):
    return source_policy(data_dir).allows(paper)

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


# Hotspot mode (the default recommendation path): recent papers, newest favoured. These apply only while the owner
# has not chosen a time preference or a new-paper weight.
HOTSPOT_DAYS=30
HOTSPOT_BOOST=0.5


def route_beta(data_dir):
    """Learning-map mode is available only after the owner switches it on in Settings (beta, default off)."""
    return read(data_dir).get('routeBeta') is True


def hotspot_since(data_dir,today=None):
    today=today or datetime.date.today()
    return since(data_dir,today,default=(today-datetime.timedelta(days=HOTSPOT_DAYS)).isoformat())


def validate(values):
    """Reject invalid visible preferences rather than storing a value the UI cannot consume."""
    if not isinstance(values,dict):raise ValueError('settings must be an object')
    for key,(low,high,integer) in {'recommendCount':(1,20,True),'decayWindow':(7,365,True),'newPaperBoost':(0,1,False)}.items():
        if key in values:
            v=values[key]
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not low<=v<=high or (integer and int(v)!=v):
                raise ValueError(f'{key} must be between {low} and {high}')
    for key in ('sourceArxiv','sourceOpenAlex','routeBeta'):
        if key in values and not isinstance(values[key],bool):raise ValueError(f'{key} must be boolean')
    for key,allowed in {'theme':('light','dark','auto'),'language':('zh-CN','en-US'),'timePreference':('recent','month','all'),'updateFrequency':('daily','weekly','manual'),'apiProvider':('deepseek',)}.items():
        if key in values and values[key] not in allowed:raise ValueError(f'Invalid {key}')
    return dict(values)


def source_allowed(data_dir,paper):
    arxiv,general=sources(data_dir)
    is_arxiv=bool(paper.get('arxiv_id')) or 'arxiv' in str(paper.get('source') or '').casefold()
    return arxiv if is_arxiv else general

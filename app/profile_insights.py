"""Local profile presentation: explicit facts, bounded responses, no model calls."""
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from . import ranking

KINDS = {'saved', 'positive', 'negative', 'too_hard', 'understood', 'seed', 'term', 'feedback', 'week', 'exposed'}
LABELS = {'positive': '有用', 'negative': '不相关', 'too_hard': '太难', 'understood': '已读懂', 'saved': '收藏', 'exposed': '曝光'}
INTEREST = ('useful', 'irrelevant')   # a later 'understood' or 'too_hard' never replaces one of these
STOP = {'further', 'framework', 'model', 'models', 'using', 'propose', 'proposed', 'approach'}


def context(app, project_id):
    project_id = project_id or app.get_default_project_id()
    project = app.projects.get_project(project_id)
    if not project:
        raise ValueError('项目不存在')
    c = app.store.conn
    papers = {r['key']: dict(r) for r in c.execute('''
        SELECT p.* FROM project_papers pp JOIN papers p ON p.key=pp.paper_key
        WHERE pp.project_id=?
    ''', (project_id,))}
    feedback = [dict(r) for r in c.execute('''SELECT f.* FROM feedback f
        JOIN project_papers pp ON pp.project_id=f.project_id AND pp.paper_key=f.paper_key
        WHERE f.project_id=? ORDER BY f.id''', (project_id,))]
    latest, familiar = {}, {}   # the latest interest label and the latest familiarity label, each on its own
    for r in feedback:
        if not r['undone']:
            (latest if r['action'] in INTEREST else familiar)[r['paper_key']] = r
    saved = {r['paper_key']: dict(r) for r in c.execute('''
        SELECT l.* FROM project_library l JOIN papers p ON p.key=l.paper_key
        WHERE l.project_id=?''', (project_id,))}
    profile = app.profile(project_id)
    evidence = {}
    for key, paper in papers.items():
        sources = []
        if key in profile['positive_seeds']:
            sources.append('seed')
        if latest.get(key, {}).get('action') == 'useful':
            sources.append('useful_feedback')
        if key in saved:
            sources.append('saved')
        if sources:
            evidence[key] = sources
    events = []
    def event(key, kind, timestamp, **extra):
        if key in papers:
            p = papers[key]
            events.append(dict(key=key, title=p['title'], published=p.get('published'), kind=kind,
                               time=timestamp, sources=evidence.get(key, []), **extra))
    for r in feedback:
        if not r['undone']:
            kind = {'useful': 'positive', 'irrelevant': 'negative', 'too_hard': 'too_hard', 'understood': 'understood'}.get(r['action'], 'other')
            event(r['paper_key'], kind, r['created_at'], feedback_id=r['id'], action=r['action'], reason=r['reason'])
    for key, r in saved.items():
        event(key, 'saved', r['saved_at'])
    for r in c.execute('''SELECT e.* FROM exposures e JOIN batches b ON b.id=e.batch_id
        WHERE b.project_id=?''', (project_id,)):
        event(r['paper_key'], 'exposed', r['shown_at'])
    return dict(project_id=project_id, project=project, profile=profile, papers=papers,
                feedback=feedback, latest=latest, familiar=familiar, saved=saved, evidence=evidence, events=events,
                tree=library_tree(c, papers), route=lambda keys: learning_map(app, project_id, papers, keys))


def library_tree(conn, papers):
    """{names: {direction id: "Parent / Child"}, by_paper: {paper key: [direction ids]}} from the shared library
    categories, plain reads only. Only this project's papers are looked up; the tree itself is shared."""
    try:
        row = conn.execute("SELECT data FROM org_projects WHERE project='default'").fetchone()
        data = json.loads(row[0]) if row else {}
        parent = {d['id']: d.get('parent_id') for d in data.get('directions', [])}
        name = {d['id']: str(d['name']) for d in data.get('directions', [])}
        members = data.get('memberships', {})
    except (sqlite3.OperationalError, ValueError, KeyError, TypeError, AttributeError):   # no tables, or a record that is not what we wrote
        parent, name, members = {}, {}, {}
    def path(identifier, seen=()):
        up = parent.get(identifier)
        return (path(up, seen + (identifier,)) + ' / ' if up in name and up not in seen else '') + name[identifier]
    return dict(names={i: path(i) for i in name},
                by_paper={k: [i for i in members.get(k, []) if i in name] for k in papers})


def learning_map(app, project_id, papers, keys):
    """The project's learning map with progress, and the unit each of the papers in `keys` fits best, or None without
    a map (or when the stored map cannot be read: the report then simply has no learning-map section). Only the
    papers that had a record this week are matched, so a large library costs nothing extra."""
    from . import pathgrowth
    try:
        state = app.route_get(project_id)
        graph = state.get('graph')
        if not graph:
            return None
        live = {**graph, 'concepts': [c for c in graph['concepts'] if c.get('state', 'active') == 'active']}
        best = {key: ids[0] for key, ids in pathgrowth.assign(live, [dict(papers[k]) for k in keys if k in papers]).items()}
        units = {c['id']: dict(c, name=str(c['name'])) for c in live['concepts']}
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return dict(units=units, progress=state.get('progress') or {}, best=best,
                done=state.get('done', 0), total=state.get('total', 0), enabled=bool(state.get('enabled')))


def stamp(value):
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except (TypeError, ValueError, AttributeError):
        return None


def period_events(ctx, start, end):
    return [e for e in ctx['events'] if stamp(e['time']) and start <= stamp(e['time']) < end]


def boundary():
    # Calendar days, UTC; identical windows throughout a day and no sliding bucket labels.
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)


def keywords(ctx, stopwords):
    docs = defaultdict(set)
    for key in ctx['evidence']:
        p = ctx['papers'][key]
        for term in set(ranking.words((p['title'] or '') + ' ' + (p['abstract'] or ''))) - stopwords - STOP:
            docs[term].add(key)
    top = sorted(docs, key=lambda t: (-len(docs[t]), t))[:20]
    maximum = max((len(docs[t]) for t in top), default=1)
    return [dict(term=t, score=len(docs[t])/maximum, documents=len(docs[t]), explicit=False,
                 sources=sorted({s for k in docs[t] for s in ctx['evidence'][k]}),
                 evidence_keys=sorted(docs[t])[:5]) for t in top]


WEEK_KINDS = ('saved', 'positive', 'understood', 'negative', 'too_hard', 'exposed')
SIGNAL_KINDS = ('saved', 'positive', 'understood')   # explicit "I want this / I understood this"
MAX_DIRECTIONS = 12
MAX_DIRECTION_PAPERS = 6


def _tally(events):
    count = Counter(e['kind'] for e in events)
    return {k: count[k] for k in WEEK_KINDS}


def weekly_days(start, events):
    """Seven UTC calendar days from `start`, each with a count per kind, so the week reads as a shape."""
    days = []
    for i in range(7):
        a, b = start + timedelta(days=i), start + timedelta(days=i + 1)
        days.append(dict(date=a.date().isoformat(), weekday=a.weekday(),
                         **_tally([e for e in events if stamp(e['time']) and a <= stamp(e['time']) < b])))
    return days


def _by_direction(ctx, events):
    tree, out = ctx['tree'], {}
    for e in events:
        if e['kind'] not in WEEK_KINDS:
            continue
        for d in tree['by_paper'].get(e['key']) or ['']:
            group = out.setdefault(d, {'events': [], 'keys': set(), 'signal': set()})
            group['events'].append(e)
            if e['kind'] != 'exposed':
                group['keys'].add(e['key'])
            if e['kind'] in SIGNAL_KINDS:
                group['signal'].add(e['key'])
    return out


def _direction_status(now, before, acted):
    """now / before: papers with an explicit positive record in each week; acted: any record this week besides
    being shown. "quiet" means there is no record at all this week (never "less interest"); a week with only
    not-relevant or too-hard records is "other"."""
    if now and not before:
        return 'new'
    if now > before:
        return 'more'
    if now == before and now:
        return 'same'
    if now:
        return 'fewer'
    return 'other' if acted or not before else 'quiet'


def weekly_directions(ctx, current, previous):
    """What moved in each library category (a paper in two categories counts in both): this week's and last week's
    explicit records, the papers behind them and a neutral word for the change. Counts of the person's own records."""
    a, b = _by_direction(ctx, current), _by_direction(ctx, previous)
    rows = []
    for d in a.keys() | b.keys():
        now, before = a.get(d), b.get(d)
        if not ((now and now['keys']) or (before and before['keys'])):
            continue   # only "shown" in both weeks: nothing the person did
        kinds = defaultdict(set)
        for e in (now['events'] if now else []):
            if e['kind'] != 'exposed':
                kinds[e['key']].add(e['kind'])
        titles = {k: ctx['papers'][k]['title'] or k for k in kinds}
        papers = [dict(key=k, title=titles[k], kinds=sorted(kinds[k])) for k in sorted(kinds, key=lambda k: (-len(kinds[k]), titles[k], k))]
        rows.append(dict(
            id=d, name=ctx['tree']['names'].get(d, '未分类'),
            current=dict(_tally(now['events'] if now else []), papers=len(now['keys']) if now else 0),
            previous=dict(_tally(before['events'] if before else []), papers=len(before['keys']) if before else 0),
            status=_direction_status(len(now['signal']) if now else 0, len(before['signal']) if before else 0, bool(now and now['keys'])),
            papers=papers[:MAX_DIRECTION_PAPERS], more=max(0, len(papers) - MAX_DIRECTION_PAPERS)))
    rows.sort(key=lambda r: (-r['current']['papers'], -(r['current']['saved'] + r['current']['positive'] + r['current']['understood']),
                             -r['previous']['papers'], r['name']))
    return rows


def weekly_units(ctx, events):
    """The learning map's units with this week's explicit evidence and the overall progress; None without a map.
    Saving shows interest and does not advance a unit: a unit is advanced only by an "understood" this week."""
    route = ctx['route']({e['key'] for e in events})
    if not route:
        return None
    tally = {unit: dict(understood=0, positive=0, negative=0, too_hard=0, papers=set()) for unit in route['units']}
    for e in events:
        unit = route['best'].get(e['key'])
        if unit in tally and e['kind'] in ('understood', 'positive', 'negative', 'too_hard'):
            tally[unit][e['kind']] += 1
            tally[unit]['papers'].add(e['key'])
    items = []
    for i, c in route['units'].items():
        t = tally[i]
        items.append(dict(id=i, name=c['name'], type=c.get('type'), status=(route['progress'].get(i) or {}).get('status', 'locked'),
                          current=dict({k: v for k, v in t.items() if k != 'papers'}, papers=len(t['papers']))))
    return dict(items=items, done=route['done'], total=route['total'], enabled=route['enabled'],
                advanced=[u['name'] for u in items if u['current']['understood']])


def weekly_highlights(ctx, current, previous, directions, units):
    keys = lambda events: {e['key'] for e in events if e['kind'] != 'exposed'}
    # the explicit rating of a paper this week is its latest one: useful then not-relevant counts once, as not relevant
    rating = {}
    for e in current:
        if e['kind'] in ('positive', 'negative'):
            rating[e['key']] = max(rating.get(e['key'], (e['time'] or '', 0, e['kind'])), (e['time'] or '', e.get('feedback_id', 0), e['kind']))
    count = Counter(kind for _, _, kind in rating.values())
    seen = {e['key'] for e in current if e['kind'] == 'exposed'}
    return dict(papers=len(keys(current)), previous_papers=len(keys(previous)),
                directions=sum(1 for d in directions if d['current']['papers']),
                positive=count['positive'], negative=count['negative'], judged=count['positive'] + count['negative'],
                seen=len(seen), seen_acted=len(seen & keys(current)),
                units_advanced=len(units['advanced']) if units else None)


def weekly_picks(ctx, events, limit=10):
    """The papers the person saved or marked understood this week, newest first, with where they sit."""
    kinds, latest = defaultdict(set), {}
    for e in events:
        if e['kind'] in SIGNAL_KINDS:
            kinds[e['key']].add(e['kind'])
            latest[e['key']] = max(latest.get(e['key'], ''), e['time'] or '')
    route = ctx['route'](set(kinds))
    picks = []
    for key in sorted(kinds, key=lambda k: (latest[k], k), reverse=True)[:limit]:
        paper = ctx['papers'][key]
        unit = route['best'].get(key) if route else None
        picks.append(dict(key=key, title=paper['title'] or key, published=paper.get('published'), kinds=sorted(kinds[key]),
                          directions=[ctx['tree']['names'][d] for d in ctx['tree']['by_paper'].get(key, [])] or ['未分类'],
                          unit=route['units'][unit]['name'] if unit in (route['units'] if route else {}) else None))
    return picks


def weekly(ctx):
    end = boundary()
    start, prev = end-timedelta(days=7), end-timedelta(days=14)
    current_events, previous_events = period_events(ctx, start, end), period_events(ctx, prev, start)
    def counts(events):
        cnt = Counter(e['kind'] for e in events)
        return {**{k: cnt[k] for k in LABELS}, 'feedback': sum('feedback_id' in e for e in events),
                'activity': len(events), 'total_saved': len(ctx['saved'])}
    def terms(events):
        keys = {e['key'] for e in events if e['kind'] in ('saved', 'positive')}
        from .service import PROFILE_STOPWORDS
        counter = Counter()
        for key in keys:
            p = ctx['papers'][key]
            counter.update(set(ranking.words(f"{p['title'] or ''} {p['abstract'] or ''}"))-PROFILE_STOPWORDS-STOP)
        return counter
    a, b = terms(current_events), terms(previous_events)
    changes = [dict(term=t, current=a[t], previous=b[t], delta=a[t]-b[t]) for t in a.keys() | b.keys()]
    changes.sort(key=lambda r: (-abs(r['delta']), -r['current'], r['term']))
    all_directions = weekly_directions(ctx, current_events, previous_events)
    directions = all_directions[:MAX_DIRECTIONS]
    units = weekly_units(ctx, current_events)
    return dict(week_start=start.isoformat(), week_end=end.isoformat(), previous_start=prev.isoformat(),
                stats=counts(current_events), previous_stats=counts(previous_events),
                has_activity=bool(current_events), comparable=bool(current_events and previous_events),
                daily=weekly_days(start, current_events), directions=directions, more_directions=len(all_directions) - len(directions), units=units,
                highlights=weekly_highlights(ctx, current_events, previous_events, all_directions, units),
                picks=weekly_picks(ctx, current_events),
                keyword_changes={name: [r for r in changes if fn(r['delta'])][:5] for name, fn in
                                 [('rising', lambda d: d>0), ('stable', lambda d: d==0), ('falling', lambda d: d<0)]})


def insights(app, project_id, weeks=12):
    ctx = context(app, project_id)
    end = boundary()
    start = end-timedelta(weeks=weeks)
    buckets = []
    for i in range(weeks):
        a, b = start+timedelta(weeks=i), start+timedelta(weeks=i+1)
        events = period_events(ctx, a, b)
        cnt = Counter(e['kind'] for e in events)
        buckets.append(dict(start=a.date().isoformat(), end=b.date().isoformat(),
                            **{k: cnt[k] for k in LABELS}, activity=len(events), interest_score=cnt['positive']-cnt['negative']))
    from .service import PROFILE_STOPWORDS
    terms = keywords(ctx, PROFILE_STOPWORDS)
    latest_counts = Counter(r['action'] for r in [*ctx['latest'].values(), *ctx['familiar'].values()])
    signals = dict(pinned=len(ctx['profile']['pinned_terms']), saved=len(ctx['saved']),
                   positive=latest_counts['useful'], negative=latest_counts['irrelevant'], too_hard=latest_counts['too_hard'], seed=len(ctx['evidence'].keys() & set(ctx['profile']['positive_seeds'])))
    recent = sorted([e for e in ctx['events'] if 'feedback_id' in e], key=lambda e: e['feedback_id'], reverse=True)[:5]
    versions = app.profile_versions(ctx['project_id'])
    last = max([e['time'] for e in ctx['events']] + [v['created_at'] for v in versions], default=None)
    summary = ('当前论文证据中常见：' + '、'.join(t['term'] for t in terms[:3]) + '。词项表示论文内容，不代表已确认的长期偏好。') if terms else '暂无论文证据形成关注词项；可以先填写固定关键词，或对论文给出明确反馈。'
    return dict(project_id=ctx['project_id'], keyword_distribution=terms,
                keyword_evidence=dict(papers=len(ctx['evidence']), sources=sorted({s for ss in ctx['evidence'].values() for s in ss})),
                timeline=dict(weeks=buckets, has_activity=any(b['activity'] for b in buckets), window_weeks=weeks),
                coverage=dict(start=start.date().isoformat(), end=end.date().isoformat(), timezone='UTC', last_activity=last, has_activity=any(b['activity'] for b in buckets)),
                signals=signals, summary=summary, recent_feedback=recent, weekly_change=weekly(ctx), versions=versions[-10:][::-1])


def evidence(app, project_id, kind, term='', start=None, end=None, offset=0):
    if kind not in KINDS or offset < 0:
        raise ValueError('无效的证据查询')
    if kind == 'term' and (start or end):
        a, b = stamp(start), stamp(end)
        if not a or not b or a >= b:
            raise ValueError('无效的日期范围')
    ctx = context(app, project_id)
    if kind in ('week', 'feedback', 'exposed') or (start and kind != 'term'):
        items = ctx['events']
        if kind == 'feedback':
            items = [e for e in items if 'feedback_id' in e]
        elif kind != 'week':
            items = [e for e in items if e['kind'] == kind]
        if start or end:
            a, b = stamp(start), stamp(end)
            if not a or not b or a >= b:
                raise ValueError('无效的日期范围')
            items = [e for e in items if stamp(e['time']) and a <= stamp(e['time']) < b]
        elif kind == 'week':
            raise ValueError('周明细需要日期范围')
    else:
        items = []
        action = {'positive': 'useful', 'negative': 'irrelevant', 'too_hard': 'too_hard', 'understood': 'understood'}.get(kind)
        for key, p in ctx['papers'].items():
            fb = (ctx['familiar'] if action in ('too_hard', 'understood') else ctx['latest']).get(key, {})
            matched = (kind=='saved' and key in ctx['saved']) or (action and fb.get('action')==action) or (kind=='seed' and key in ctx['profile']['positive_seeds'])
            if kind == 'term':
                matched = key in ctx['evidence'] and term in ranking.words(f"{p['title'] or ''} {p['abstract'] or ''}")
            if matched:
                if kind == 'term' and (start or end):
                    a, b = stamp(start), stamp(end)
                    saved_at = ctx['saved'].get(key, {}).get('saved_at')
                    fb_at = ctx['latest'].get(key, {}).get('created_at')
                    times = [stamp(t) for t in (saved_at, fb_at) if stamp(t)]
                    matched = bool(a and b and any(a <= t < b for t in times))
            if matched:
                items.append(dict(key=key, title=p['title'], published=p.get('published'), kind=kind,
                                  time=fb.get('created_at') or ctx['saved'].get(key, {}).get('saved_at'),
                                  action=fb.get('action'), feedback_id=fb.get('id'), sources=ctx['evidence'].get(key, [])))
    items = sorted(items, key=lambda r: (r.get('time') or '', r['key']), reverse=True)
    return dict(project_id=ctx['project_id'], items=items[offset:offset+25], total=len(items), offset=offset, limit=25)

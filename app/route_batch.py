"""Deterministic Route batch roles and quotas. No I/O or model calls.

An exploration topic is a discovery clue, not a claim that a new learning task
has been established. A matching routine satisfied concept is not a filler.
"""
from datetime import date

from . import learning_scope, pathgraph, pathgrowth
from .sources import clean_query

MAX_BATCH = 5
PATH_SLOTS = 3
DISCOVERY_SLOTS = 2
COMPLETED_SOURCE = 'route-completed'


def policy(completed=False):
    return {'path':0 if completed else 3,'explore':1,'watch':0 if completed else 1,
            'discovery_max':1 if completed else 2,'completed_daily_cap':1 if completed else None}


def choose(route, papers, scored, limit, directions=(), shown=None, sources=None,
           recent_since=None, today=None, evidence=None, explore_keys=None):
    """[(paper_key, concept_id | None, kind, label | None)], at most five.

    Paths can repeat until explicitly answered; discoveries always need unseen
    papers. The caller already removed answered/ineligible papers. Unmatched or
    unsatisfied side-branch papers can be explored. Papers matching current or
    satisfied concepts need a novel public exploration topic or an existing
    direction proposal to be considered exploration. Ordinary locked/satisfied
    matches are not automatically relabelled to fill a slot.
    """
    shown, sources = shown or {}, sources or {}
    limit = max(0,min(MAX_BATCH,int(limit)))
    completed = route.get('goal_status') == 'completed'
    if route.get('goal_status') not in ('learning','completed') or route.get('progress_verification_deferred'):return []
    matching_scope=route.get('matching_scope') or learning_scope.make(route.get('brief'))
    papers=[p for p in papers if learning_scope.check(matching_scope,p)['compatible']]
    graph=route['graph'];frontier=route.get('frontier') or []
    active={**graph,'concepts':[c for c in graph['concepts'] if c.get('state','active')=='active']}
    assigned=pathgrowth.assign(active,papers,matching_scope)
    score=dict(scored); by_key={p['key']:p for p in papers}
    keys=[k for k,_ in scored if k in by_key]
    def ordered(values, paths=False):
        values=sorted(values)
        values.sort(key=lambda k:str(by_key[k].get('published') or ''),reverse=True)
        if paths:
            values.sort(key=lambda k:-score.get(k,0))
            values.sort(key=lambda k:pathgrowth.paper_role(by_key[k])!='intro')
            values.sort(key=lambda k:shown.get(k,0))
        return values
    by_concept={c:[] for c in frontier};path_nodes={}
    for key in keys:
        ids=assigned.get(key,[])
        # A still-locked primary may also explicitly support an open unit.
        # The material selection does not move primary-only mastery, nor
        # recycle a satisfied primary into another routine learning slot.
        primary=ids[0] if ids else None
        cid=next((i for i in ids if i in by_concept),None) if primary and route['progress'][primary]['status']!='satisfied' else None
        if cid:
            by_concept[cid].append(key);path_nodes[key]=cid
    for c in by_concept:by_concept[c]=ordered(by_concept[c],True)
    toward={};direction_by_key={}
    for direction in directions:
        if not direction.get('positive_basis'):continue
        for key in direction['papers']:
            toward.setdefault(key,direction['name']);direction_by_key.setdefault(key,direction)
    covered={clean_query(t).casefold() for c in active['concepts'] for t in c.get('terms',[])}
    explore,watch,labels,purposes={}, {}, {}, {}
    watched=set(route.get('watched_satisfied') or [])
    scope=set(route.get('goal_scope') or [])
    for key in keys:
        if shown.get(key):continue
        ids=assigned.get(key,[])
        public=None
        for entry in reversed(sources.get(key,[])):
            query=clean_query(entry.get('query'))
            if 'explore' not in entry.get('kinds',[]) or not query or query.casefold() in covered:continue
            visible={'title':by_key[key].get('title'),'abstract':by_key[key].get('abstract')}
            matches=pathgrowth.match_evidence({'name':'Public exploration query','terms':[query]},visible)
            if matches:
                public={'kind':'public_query','query':query,'quote':matches[0]['quote'],
                        'observed_at':entry.get('observed_at')};break
        novel=public['query'] if public else None
        side=next((c for c in ids if c not in scope and route['progress'][c]['status']!='satisfied'),None)
        # An exploration paper must still mention a project keyword (owner, 2026-10-26): `explore_keys`, when given.
        if (side or novel or key in toward) and (explore_keys is None or key in explore_keys):
            explore[key]=side or (ids[0] if ids else None)
            labels[key]=toward.get(key) or novel
            if key in toward:
                direction=direction_by_key[key]
                purposes[key]={'kind':'direction_proposal','name':direction['name'],
                    'positive_basis':direction['positive_basis'][:3],'status':'pending_user_review'}
            elif public:purposes[key]=public
            else:
                node=next(c for c in active['concepts'] if c['id']==side)
                matches=pathgrowth.match_evidence(node,by_key[key],matching_scope)
                purposes[key]={'kind':'side_branch','node':side,'name':node['name'],
                               'quote':matches[0]['quote'],'state':'unsatisfied'}
        cid=next((c for c in ids if c in watched),None)
        if cid:
            published=str(by_key[key].get('published') or '')
            try:valid=date.fromisoformat(published).isoformat()==published
            except ValueError:valid=False
            if valid and (not recent_since or published>=recent_since) and (not today or published<=today):watch[key]=cid
    # Interest ranks exploration; watched developments are strictly newest.
    explore_order=ordered(explore,True)
    explore_order.sort(key=lambda k:k not in toward)
    # Five slots form a tiny matching problem. Reassign an earlier slot to
    # another eligible paper before taking a dual-role paper away from a role.
    # This preserves 3+1+1 whenever a distinct-paper assignment exists.
    slots=[]; assigned_slots={}; owners={}
    def add_slot(kind, order):
        slot=len(slots);slots.append((kind,list(order)))
        def fill(index,seen):
            order=slots[index][1]
            candidates=[key for key in order if key not in owners]+[key for key in order if key in owners]
            for key in candidates:
                if key in seen:continue
                seen.add(key)
                previous=owners.get(key)
                if previous is None or fill(previous,seen):
                    owners[key]=index;assigned_slots[index]=key;return True
            return False
        if fill(slot,set()):return True
        slots.pop();return False
    def paths(count):
        present=[c for c in frontier if by_concept[c]]
        weights=[1/(1+route['progress'][c]['shown'])*(.5 if route['progress'][c]['low_interest'] else 1) for c in present]
        all_paths=[k for c in present for k in by_concept[c]]
        for c,n in zip(present,pathgraph.allocate(count,weights)):
            for _ in range(n):add_slot('route',by_concept[c]+[k for k in all_paths if k not in by_concept[c]])
    def discovery(kind,count):
        order=explore_order if kind=='explore' else ordered(watch)
        for _ in range(count):add_slot(kind,order)
    if not completed:paths(min(PATH_SLOTS,limit))
    capacity=1 if completed else min(DISCOVERY_SLOTS,max(0,limit-PATH_SLOTS))
    discovery('explore',min(1,capacity))
    discovery('watch',max(0,capacity-sum(kind!='route' for kind,_ in slots)))
    discovery('explore',max(0,capacity-sum(kind!='route' for kind,_ in slots)))
    if not completed:paths(max(0,limit-len(slots)))
    chosen=[]
    for index,(kind,_) in enumerate(slots):
        key=assigned_slots[index]
        actual='explore_new' if kind=='explore' and key in toward else kind
        node=path_nodes[key] if kind=='route' else explore[key] if kind=='explore' else watch[key]
        chosen.append((key,node,actual,labels.get(key) if kind=='explore' else None))
        if evidence is not None and kind=='explore':evidence[key]=purposes[key]
    return chosen

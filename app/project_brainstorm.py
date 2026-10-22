"""A lightweight runtime skill for agreeing a project's research direction.

This is a conversation policy, not a tool-using agent. The preferred
sequence is goal -> scope -> starting point/time -> desired output -> review
-> confirmation. Already explicit details are skipped; readiness permits
confirmation at any time. From turn six the draft is offered for confirmation,
but the conversation has no turn cap (owner 2026-10-22) and is never a target
questionnaire. The model sees RULES verbatim. The richer local phase table only
supports the honest local fallback and tests; it is not claimed to be extra model context.
"""

RULES = ('Coach:1gap;offer focus/tradeoff+2-3 choices;unsure:suggest;skip known;'
         'turn>=6:offer confirm,keep helping/ready now;lastQ/summary;flag broad/conflict;'
         'keep choice/no inferred excludes.')
PHASES = ('goal', 'scope', 'start', 'output', 'review', 'confirm')


def plan_turn(turn, *, quick=False, known=(), ready=False):
    """A preferred phase, allowing explicitly known phases to be skipped.

    It is advisory: the actual model must also use the original goal/current
    summary to skip resolved issues. No local keyword heuristic pretends to
    understand arbitrary disciplines, and no new exclusion is inferred.
    """
    if type(turn) is not int or turn < 1:
        raise ValueError('引导轮次无效')
    if any(phase not in PHASES for phase in known):
        raise ValueError('引导阶段无效')
    phase_turn = min(len(PHASES), turn)   # past the last phase the draft stays offered for confirmation
    if quick:
        return {'turn': 0, 'phase': 'draft', 'confirm': True}
    if ready:
        return {'turn': turn, 'phase': 'confirm', 'confirm': True}
    index = phase_turn - 1
    while index < len(PHASES) - 1 and PHASES[index] in known:
        index += 1
    phase = PHASES[index]
    return {'turn': turn, 'phase': phase, 'confirm': phase == 'confirm'}


_LOCAL = {
    'scope': (('建议先从领域概览入手，再收敛一个问题。你想先聚焦哪一块？',
               ['领域概览', '方法原理', '一个应用场景']),
              ('Start with an overview, then narrow one problem. Where should we focus?',
               ['Field overview', 'Method principles', 'One application'])),
    'start': (('建议按现有基础决定读论文还是动手。你现在更接近哪种起点？',
               ['从零开始', '有基础，先读论文', '有编程基础，想复现']),
              ('Your background sets the reading effort. What is your starting point?',
               ['Starting from zero', 'Some background; read papers', 'Can code; reproduce a method'])),
    'output': (('先选一个能检查的成果；概览投入较少，复现需要更多时间。你更想得到什么？',
                ['读懂代表论文', '比较两种方法', '完成一个小复现']),
               ('Choose a checkable outcome; a reproduction takes more time. Which fits?',
                ['Understand representative papers', 'Compare two methods', 'Build a small reproduction'])),
    'review': (('建议核对目标、关键词和学习图，再决定是否补充。接下来怎么做？',
                ['核对当前草稿', '补充时间投入', '调整学习目标']),
               ('Check the goal, keywords and map before continuing. What comes next?',
                ['Review the current draft', 'Add time available', 'Adjust the learning goal'])),
    'confirm': (('当前草稿可以随时编辑。确认方向合适后，在下方检查学习图并创建。',
                 ['查看当前草稿', '调整学习目标']),
                ('Edit the draft as needed, then review the learning map before creating.',
                 ['Review the current draft', 'Adjust the learning goal'])),
}


def local_followup(draft, message, english=False):
    """Local questions use only explicit choices; they never act as AI debate.

    A supplied goal is already known, so failure cannot restart at asking the
    domain. Unrecognized free text retains the current question instead of
    guessing the person's background, time, dislikes or exclusions.
    """
    phase = draft.get('brainstorm_phase')
    if draft.get('ready') is True:
        phase = 'confirm'
    if phase not in _LOCAL:
        phase = plan_turn(1, known=['goal'])['phase']
    choices = draft.get('choices') or []
    if message in choices and phase != 'confirm':
        phase = PHASES[PHASES.index(phase) + 1]
    question, options = _LOCAL[phase][1 if english else 0]
    return {'brainstorm_phase': phase, 'next_question': question, 'choices': options,
            'ready': phase == 'confirm'}

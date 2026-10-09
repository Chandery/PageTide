#!/usr/bin/env python3
"""Offline arithmetic and usage-contract checks, not an app gateway or tokenizer."""
import argparse
import datetime as dt
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def integer(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name}: expected nonnegative integer")
    return value


def money(value, name):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name}: invalid decimal")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{name}: expected finite nonnegative decimal")
    return result


def load(root=ROOT):
    return json.loads((root / 'harness/budget.json').read_text())


def validate(config):
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('unsupported budget schema')
    provider, policy = config['provider'], config['policy']
    flags = [('approved_by_owner', config['approved_by_owner'])]
    flags += [(key, policy[key]) for key in (
        'runtime_enforcement_implemented', 'tokenizer_parity_verified',
        'budget_increase_requires_owner_approval', 'cache_savings_assumed',
        'automatic_model_fallback', 'aggregate_limits_enabled')]
    for name, value in flags:
        if type(value) is not bool:
            raise ValueError(f'{name}: expected JSON boolean, not truthy text')
    if provider is not None:
        if integer(provider['recheck_after_days'], 'recheck_after_days') == 0:
            raise ValueError('recheck_after_days must be positive')
        dt.date.fromisoformat(provider['verified_on'])
        if provider['thinking'] != 'disabled':
            raise ValueError('default workflow must disable thinking')
        for key in ('input_miss', 'input_hit', 'output'):
            money(provider['usd_per_million'][key], key)
    if policy['automatic_model_fallback']:
        raise ValueError('default workflow must disable fallback')
    if policy['cache_savings_assumed']:
        raise ValueError('baseline cannot assume cache savings')
    for key in ('daily_background_tokens', 'daily_interactive_tokens',
                'daily_total_tokens', 'monthly_total_tokens', 'max_retries_per_operation'):
        integer(policy[key], key)
    for key in ('daily_usd', 'monthly_usd'):
        money(policy[key], key)
    if not 0 < money(policy['warning_fraction'], 'warning_fraction') < 1:
        raise ValueError('warning fraction must lie between zero and one')
    if not isinstance(config['operations'], dict) or not config['zero_token_operations']:
        raise ValueError('operations and zero-token maintenance must be explicit')
    if provider is None:
        if config['operations'] != {} or any(policy[key] != 0 for key in (
                'daily_background_tokens', 'daily_interactive_tokens', 'daily_total_tokens',
                'monthly_total_tokens', 'max_retries_per_operation')) or any(
                money(policy[key], key) != 0 for key in ('daily_usd', 'monthly_usd')):
            raise ValueError('no provider requires empty operations and zero model limits/retries')
        if policy['runtime_enforcement_implemented'] or policy['tokenizer_parity_verified']:
            raise ValueError('no provider cannot claim runtime enforcement or tokenizer parity')
    elif not config['operations']:
        raise ValueError('configured provider requires explicit operations')
    prompt_paths = set()
    for name, op in config['operations'].items():
        if op['trigger'] not in ('background', 'interactive'):
            raise ValueError(f'{name}: unknown trigger')
        if op['prompt'] in prompt_paths:
            raise ValueError('duplicate prompt registration')
        prompt_paths.add(op['prompt'])
        for axis in ('input', 'output'):
            ref = integer(op['reference'][axis], name)
            cap = integer(op['cap'][axis], name)
            if ref > cap or cap == 0:
                raise ValueError(f'{name}: reference must be <= positive cap')
        components = [integer(v, name) for v in op['input_cap_components'].values()]
        if sum(components) != op['cap']['input']:
            raise ValueError(f'{name}: input component envelope does not add up')
    ids = set()
    for scenario in config['scenarios']:
        if scenario['id'] in ids:
            raise ValueError('duplicate scenario id')
        ids.add(scenario['id'])
        if not 1 <= integer(scenario['days'], 'days') <= 31:
            raise ValueError('scenario must fit one calendar month (1..31 days)')
        weeks = integer(scenario['weekly_runs'], 'weekly_runs')
        if weeks > (scenario['days'] + 6) // 7:
            raise ValueError('weekly runs exceed supported calendar; represent retries as calls')
        for period in ('daily_calls', 'weekly_calls', 'one_off_calls'):
            for name, count in scenario[period].items():
                integer(count, name)
                if name not in config['operations']:
                    raise ValueError(f'unregistered operation: {name}')
    evaluation = config.get('evaluation')
    if evaluation is not None:
        validate_evaluation(evaluation)


def validate_evaluation(evaluation):
    """Annotator profile: tokens only, never USD, and never part of the shipped app."""
    provider = evaluation['provider']
    if provider['price_verifiable'] is not False:
        raise ValueError('evaluation provider prices must be marked unverifiable until a public source exists')
    integer(provider['observed_hidden_input_tokens'], 'observed_hidden_input_tokens')
    dt.date.fromisoformat(provider['verified_on'])
    if integer(provider['recheck_after_days'], 'recheck_after_days') == 0:
        raise ValueError('evaluation recheck interval must be positive')
    operations = evaluation['operations']
    if not isinstance(operations, dict) or not operations:
        raise ValueError('evaluation section requires operations')
    for name, op in operations.items():
        for axis in ('input', 'output'):
            ref = integer(op['reference'][axis], name)
            cap = integer(op['cap'][axis], name)
            if ref > cap or cap == 0:
                raise ValueError(f'evaluation {name}: reference must be <= positive cap')
        components = [integer(v, name) for v in op['input_cap_components'].values()]
        if sum(components) != op['cap']['input']:
            raise ValueError(f'evaluation {name}: input component envelope does not add up')
    ids = set()
    for scenario in evaluation['scenarios']:
        if scenario['id'] in ids:
            raise ValueError('duplicate evaluation scenario id')
        ids.add(scenario['id'])
        for name, count in scenario['calls'].items():
            integer(count, name)
            if name not in operations:
                raise ValueError(f'unregistered evaluation operation: {name}')


def cost(config, input_tokens, output_tokens, cache_hits=0):
    integer(input_tokens, 'input')
    integer(output_tokens, 'output')
    integer(cache_hits, 'cache_hits')
    if cache_hits > input_tokens:
        raise ValueError('cache hits exceed input')
    if config['provider'] is None:
        if input_tokens or output_tokens:
            raise ValueError('cannot price model usage without a configured provider')
        return Decimal(0)
    prices = config['provider']['usd_per_million']
    return ((input_tokens - cache_hits) * money(prices['input_miss'], 'miss')
            + cache_hits * money(prices['input_hit'], 'hit')
            + output_tokens * money(prices['output'], 'output')) / Decimal(1000000)


def totals(config, calls, mode):
    result = {'input': 0, 'output': 0, 'background': 0, 'interactive': 0}
    for name, count in calls.items():
        integer(count, name)
        op = config['operations'][name]
        inp, out = op[mode]['input'] * count, op[mode]['output'] * count
        result['input'] += inp
        result['output'] += out
        result[op['trigger']] += inp + out
    result['tokens'] = result['input'] + result['output']
    result['usd'] = cost(config, result['input'], result['output'])
    return result


def scenario_totals(config, scenario, mode):
    calls = {}
    for period, multiplier in (('daily_calls', scenario['days']),
                               ('weekly_calls', scenario['weekly_runs']),
                               ('one_off_calls', 1)):
        for name, count in scenario[period].items():
            calls[name] = calls.get(name, 0) + count * multiplier
    return totals(config, calls, mode)


def peak_day(config, scenario, mode):
    calls = dict(scenario['daily_calls'])
    periods = ['one_off_calls']
    if scenario['weekly_runs']:
        periods.append('weekly_calls')
    for period in periods:
        for name, count in scenario[period].items():
            calls[name] = calls.get(name, 0) + count
    return totals(config, calls, mode)


def violations(config, scenario, mode):
    day, month, p = peak_day(config, scenario, mode), scenario_totals(config, scenario, mode), config['policy']
    if not p.get('aggregate_limits_enabled', True):
        return []
    result = []
    for field, key in (('tokens', 'daily_total_tokens'), ('background', 'daily_background_tokens'),
                       ('interactive', 'daily_interactive_tokens')):
        if day[field] > p[key]:
            result.append(key)
    if day['usd'] > money(p['daily_usd'], 'daily_usd'):
        result.append('daily_usd')
    if month['tokens'] > p['monthly_total_tokens']:
        result.append('monthly_total_tokens')
    if month['usd'] > money(p['monthly_usd'], 'monthly_usd'):
        result.append('monthly_usd')
    return result


def reconcile_usage(config, usage):
    """Validate documented counts; reasoning is a subset, not an additional bill."""
    inp = integer(usage['prompt_tokens'], 'prompt_tokens')
    out = integer(usage['completion_tokens'], 'completion_tokens')
    hit = integer(usage['prompt_cache_hit_tokens'], 'cache_hit')
    miss = integer(usage['prompt_cache_miss_tokens'], 'cache_miss')
    total = integer(usage['total_tokens'], 'total_tokens')
    reasoning = integer(usage.get('completion_tokens_details', {}).get('reasoning_tokens', 0), 'reasoning')
    if hit + miss != inp or inp + out != total or reasoning > out:
        raise ValueError('inconsistent provider usage; do not silently bill zero')
    cached = usage.get('prompt_tokens_details', {}).get('cached_tokens', hit)
    integer(cached, 'cached_tokens')
    if cached != hit:
        raise ValueError('cached token representations disagree')
    return {'tokens': total, 'usd': cost(config, inp, out, hit)}


def can_admit(settled, reservations, request, limit):
    """Arithmetic contract fixture; persistence and transaction safety are NOT provided."""
    for name, value in [('settled', settled), ('request', request), ('limit', limit)]:
        integer(value, name)
    for value in reservations:
        integer(value, 'reservation')
    return settled + sum(reservations) + request <= limit


def render(config):
    validate(config)
    if config['provider'] is None:
        return '\n'.join([
            '# 模型调用边界（生成文件）', '',
            f"基线 `{config['baseline_id']}`。",
            '运行 `python3 scripts/budget.py --write` 生成。不要手动编辑。', '',
            '未选择模型供应商，操作注册表为空；旧阅读器/问答/周报配置已删除。',
            '模型token及USD日/月限额均为0，重试为0；不代表全部运行成本为0。',
            '没有应用网关或tokenizer校准；预算与实施批准不继承旧方案。',
            '这里只检查配置和文档一致性，不是运行时拦截、账单或产品测量。',
            '公开元数据API费用、私人种子外发、计算资源和开发agent用量另算另批。',
            '将来引入模型须重新登记供应商/价格/操作/限额并验证网关、取得授权。', ''
        ])
    lines = [
        '# 可复算预算表（生成文件）', '',
        f"基线 `{config['baseline_id']}`；来源核查 {config['provider']['verified_on']}。",
        '运行 `python3 scripts/budget.py --write` 生成。不要手动编辑。', '',
        '**参考量是未实测的目标长度，上限是拟实施请求 envelope；不是账单或质量保证。**',
        '不假设缓存命中或低峰优惠。维护/检索/数据库不调用模型；无AI模式不产生新AI解读。', '',
        '## 每次操作', '',
        '| 操作 | 参考输入 | 参考输出 | 上限输入 | 上限输出 | 参考USD | 上限USD |',
        '|---|---:|---:|---:|---:|---:|---:|'
    ]
    for name, op in config['operations'].items():
        r, c = op['reference'], op['cap']
        lines.append(f"| {name} | {r['input']:,} | {r['output']:,} | {c['input']:,} | {c['output']:,} | {cost(config,r['input'],r['output']):.6f} | {cost(config,c['input'],c['output']):.6f} |")
    lines += ['', '## 场景（参考量和请求上限均不含额外隐式调用）', '',
              '每行显示实际配置的天数/周任务批次数。峰值日把周任务和一次性操作完整计入当天，不用摊销值做准入。', '',
              '| 场景/口径 | 期间输入 | 期间输出 | 期间总token | 峰值日token | 期间USD | 日/月总帽策略 |',
              '|---|---:|---:|---:|---:|---:|---|']
    for s in config['scenarios']:
        for mode, label in [('reference', '参考'), ('cap', '上限')]:
            t, d = scenario_totals(config, s, mode), peak_day(config, s, mode)
            errors = violations(config, s, mode)
            result = ('日/月总预算上限已取消；本行仅为用量算术' if not config['policy'].get('aggregate_limits_enabled', True)
                      else '会拒绝部分请求：' + ', '.join(errors) if errors else '此场景内未超限（不代表已授权）')
            period = f"{s['days']}天/{s['weekly_runs']}次周任务"
            lines.append(f"| {s['label']} / {label} / {period} | {t['input']:,} | {t['output']:,} | {t['tokens']:,} | {d['tokens']:,} | {t['usd']:.6f} | {result} |")
    p = config['policy']
    approval = 'owner 已批准' if config['approved_by_owner'] else '待用户批准'
    if not p.get('aggregate_limits_enabled', True):
        lines += ['', f'## 当前准入策略（{approval}）', '',
                  '日/月总预算上限已取消；不因历史每日/月 token 或 USD 数值拒绝运行时请求。',
                  '旧55,000/日、1,500,000/月 token 及 $0.15/日、$1.50/月保留为历史记录，不是当前上限、余额或0额度。',
                  '每操作单次输入/输出合同、显式授权和开关仍生效；开发模式保留独立开发上限与独立账本。',
                  '所有请求仍预留并记账；未知用量保持未结算预留，不称为实测或零消耗。']
    else:
        lines += ['', f'## 准入阈值（{approval}；待应用网关实现）', '',
              f"后台/日 {p['daily_background_tokens']:,}；交互/日 {p['daily_interactive_tokens']:,}；合计/日 {p['daily_total_tokens']:,}；合计/月 {p['monthly_total_tokens']:,} token。",
              f"金额额外阈值：${p['daily_usd']}/日，${p['monthly_usd']}/月；token和金额必须同时通过。",
              '后台和交互限额不相加成为总限额。已发出但用量未知的请求持续占用预留。']
    lines += [f"注册每操作最多额外尝试{p['max_retries_per_operation']}次；网关不会自动重试，重新触发仍单独准入和记账。压力场景只是需求算术，不扩大单次合同或触发授权。", '',
              '## 解释', '',
              '最低模型开销为0（本地基础模式或无需新模型结果）。',
              '日/周任务量以操作表与场景配置为准；周归一化日均不能代替实际日历累计或周报日准入。',
              '这是计划口径，不是文本实测或最低质量成本；周报执行日必须预留完整操作。',
              '不含论文API收费、税/汇率、开发agent、OCR/图片、额外embedding或未登记调用。',
              '准入算术检查不验证并发事务、真实token计数、服务商账单或模型输出质量。', '']
    evaluation = config.get('evaluation')
    if evaluation:
        prefix = evaluation['provider']['observed_hidden_input_tokens']
        lines += ['', '## 离线评估标注（非运行时；价格不可核验，只报 token）', '',
                  f"裁判 provider `{evaluation['provider']['name']}` / `{evaluation['provider']['model']}`；观测到每次请求约 {prefix:,} 个隐藏输入 token。",
                  '该 provider 无公开价格表，因此本表**不计算 USD**；只用于构建评估标签，不进入 App。', '',
                  '| 操作 | 参考输入 | 上限输入 | 上限输出 | 含隐藏前缀的每次输入上限 |', '|---|---:|---:|---:|---:|']
        for name, op in evaluation['operations'].items():
            lines.append(f"| {name} | {op['reference']['input']:,} | {op['cap']['input']:,} | {op['cap']['output']:,} | {op['cap']['input'] + prefix:,} |")
        lines += ['', '| 场景 | 调用数 | 上限输入token | 上限输出token | 上限合计token |', '|---|---:|---:|---:|---:|']
        for scenario in evaluation['scenarios']:
            calls = inp = out = 0
            for name, count in scenario['calls'].items():
                op = evaluation['operations'][name]
                calls += count
                inp += count * (op['cap']['input'] + prefix)
                out += count * op['cap']['output']
            lines.append(f"| {scenario['label']} | {calls} | {inp:,} | {out:,} | {inp + out:,} |")
        lines += ['', '评估标注是**实验开销**，不占用运行时日/月额度；要控成本就缩小留出集或每批篇数。', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--write', action='store_true')
    group.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    try:
        content = render(load())
        path = ROOT / 'docs/BUDGET.generated.md'
        if args.write:
            path.write_text(content)
            print('Wrote docs/BUDGET.generated.md')
        elif args.check:
            if not path.exists() or path.read_text() != content:
                raise ValueError('generated budget is stale; run --write and review the diff')
            print('PASS budget arithmetic and generated document parity (no live API)')
        else:
            print(content)
        return 0
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        print(f'FAIL budget: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

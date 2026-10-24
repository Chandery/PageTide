"""Worst-case price arithmetic for the registered operations (USD), used by the cost-ceiling tests."""
from decimal import Decimal


def cost(config, input_tokens, output_tokens, cache_hits=0):
    prices = config['provider']['usd_per_million']
    return ((input_tokens - cache_hits) * Decimal(str(prices['input_miss']))
            + cache_hits * Decimal(str(prices['input_hit']))
            + output_tokens * Decimal(str(prices['output']))) / Decimal(1000000)

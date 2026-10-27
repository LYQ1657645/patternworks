"""Safe provider error classification and bounded rate-limit scheduling."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import random
import re


def rate_limit_details(error):
    body = getattr(error, 'body', None)
    body = body if isinstance(body, dict) else {}
    nested = body.get('error', {})
    nested = nested if isinstance(nested, dict) else {}
    codes = {str(getattr(error, 'code', '')), str(body.get('code', '')),
             str(body.get('type', '')), str(nested.get('code', '')), str(nested.get('type', ''))}
    if codes & {'insufficient_quota', 'billing_hard_limit_reached', 'usage_limit_reached'}:
        return 'LLM_QUOTA', 'The OpenAI project has insufficient quota. Ask the owner to check billing and usage limits.', False, None
    headers = error.response.headers
    delays = []
    for name, divisor in [('retry-after-ms', 1000), ('retry-after', 1)]:
        value = headers.get(name)
        if not value:
            continue
        try:
            delay = float(value) / divisor
        except ValueError:
            try:
                date = parsedate_to_datetime(value)
                delay = (date - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                continue
        if math.isfinite(delay) and delay > 0:
            delays.append(delay)
    for resource in ('requests', 'tokens'):
        # A reset matters only when that particular bucket is exhausted.
        if headers.get(f'x-ratelimit-remaining-{resource}') != '0':
            continue
        value = headers.get(f'x-ratelimit-reset-{resource}', '')
        if re.fullmatch(r'(?:\d+(?:\.\d+)?(?:ms|s|m|h))+', value):
            delay = sum(float(number) * {'ms': .001, 's': 1, 'm': 60, 'h': 3600}[unit]
                        for number, unit in re.findall(r'(\d+(?:\.\d+)?)(ms|s|m|h)', value))
            if math.isfinite(delay):
                delays.append(delay)
    delay = math.ceil(max(delays)) if delays else None
    if delay and delay > 900:
        return 'LLM_RATE_LIMIT', 'OpenAI requires a longer cooldown. Retry this task later; the source data is unchanged.', False, delay
    return 'LLM_RATE_LIMIT', 'OpenAI is rate limited. Retry this task after the cooldown; the source data is unchanged.', True, delay


def retry_delay(problem, retries):
    if problem.code == 'LLM_RATE_LIMIT':
        return max(getattr(problem, 'retry_after', None) or 0, 60 * 2 ** min(retries, 3)) + random.randint(0, 5)
    return 2 ** (retries + 1)

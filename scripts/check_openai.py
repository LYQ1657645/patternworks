#!/usr/bin/env python3
"""Explicit, small live API check. Does not transmit S3 credentials or files."""
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, APIError

load_dotenv(Path(__file__).resolve().parent.parent / '.env.local')
if not os.environ.get('OPENAI_API_KEY'):
    raise SystemExit('OpenAI API key is not configured.')
try:
    response = OpenAI(timeout=20, max_retries=0).responses.create(
        model=os.environ.get('OPENAI_MODEL', 'gpt-4.1-mini'),
        input='Reply with the single word OK.', max_output_tokens=16, store=False,
    )
    if response.output_text.strip().upper() != 'OK':
        raise SystemExit('API responded, but the check did not return the expected word.')
except APIError as exc:
    # Avoid SDK message/body output, which may contain sensitive request details.
    print('OpenAI check failed:', type(exc).__name__, 'HTTP', getattr(exc, 'status_code', 'unavailable'))
    raise SystemExit(1) from None
print('OpenAI live check passed (minimal request; response body hidden).')

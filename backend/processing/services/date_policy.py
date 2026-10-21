"""Independent, locale-free calendar checks for the compact date-normalization tool."""
from datetime import date
import re

MONTHS = {name: index for index, names in enumerate((
    ('jan', 'january'), ('feb', 'february'), ('mar', 'march'), ('apr', 'april'), ('may',),
    ('jun', 'june'), ('jul', 'july'), ('aug', 'august'), ('sep', 'sept', 'september'),
    ('oct', 'october'), ('nov', 'november'), ('dec', 'december')), 1) for name in names}


def expected_date(value, order):
    """Return (ISO date or None, status); never infer missing years or relative dates."""
    if value is None or not value.strip():
        return None, 'missing'
    value = value.strip()
    match = re.fullmatch(r'(\d{4})([-/.])(\d{1,2})\2(\d{1,2})', value)
    chinese = re.fullmatch(r'(\d{4})年(\d{1,2})月(\d{1,2})日?', value)
    numeric = re.fullmatch(r'(\d{1,2})([-/.])(\d{1,2})\2(\d{4})', value)
    words = re.fullmatch(r'(\d{1,2})(?:st|nd|rd|th)?[ -]+([A-Za-z]+)[, -]+(\d{4})', value, re.I)
    american = re.fullmatch(r'([A-Za-z]+)[ -]+(\d{1,2})(?:st|nd|rd|th)?[, -]+(\d{4})', value, re.I)
    if match:
        year, month, day = int(match[1]), int(match[3]), int(match[4])
    elif chinese:
        year, month, day = map(int, chinese.groups())
    elif numeric:
        a, b, year = int(numeric[1]), int(numeric[3]), int(numeric[4])
        if a < 1 or b < 1 or year < 1:
            return None, 'invalid'
        if a <= 12 and b <= 12 and a != b and order == 'REJECT':
            return None, 'ambiguous'
        if a > 12 or (a <= 12 and b <= 12 and order != 'MONTH_FIRST'):
            day, month = a, b
        else:
            month, day = a, b
    elif words or american:
        if words:
            day, name, year = int(words[1]), words[2].lower(), int(words[3])
        else:
            name, day, year = american[1].lower(), int(american[2]), int(american[3])
        month = MONTHS.get(name, 0)
    else:
        return None, 'invalid'
    try:
        return date(year, month, day).isoformat(), 'normalized'
    except ValueError:
        return None, 'invalid'

"""Pure RE2 logic shared by validation, local preview and Spark Python workers.

No Django, network, dataset paths or credentials may enter this module.
"""
from functools import lru_cache
import re2

POLICY_VERSION = 're2-v1'
PATTERN_LIMIT = 512
REPLACEMENT_LIMIT = 256
CELL_LIMIT = 65536


class RuleValidationError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


@lru_cache(maxsize=32)
def compile_pattern(pattern, ignore_case):
    options = re2.Options()
    options.log_errors = False
    options.max_mem = 2 * 1024 * 1024
    options.case_sensitive = not ignore_case
    return re2.compile(pattern, options=options)


def _check_repetition(pattern):
    # Conservative product policy on top of RE2's non-backtracking execution.
    # Track repetition inside groups; classes and escaped metacharacters are atoms.
    groups, previous_repeat, index = [False], False, 0
    while index < len(pattern):
        char = pattern[index]
        if char == '\\':
            if index + 1 < len(pattern) and pattern[index + 1] in {'Q', 'E', 'C'}:
                raise RuleValidationError('REGEX_UNSUPPORTED', 'Use ordinary escaped characters, not byte matching or quoted blocks.')
            index += 2
            previous_repeat = False
            continue
        if char == '[':
            index += 1
            if index < len(pattern) and pattern[index] == '^':
                index += 1
            if index < len(pattern) and pattern[index] == ']':
                index += 1
            while index < len(pattern):
                if pattern[index] == '\\':
                    index += 2
                elif pattern[index] == ']':
                    index += 1
                    break
                else:
                    index += 1
            previous_repeat = False
            continue
        if char == '(':
            if pattern.startswith('(?', index) and not pattern.startswith('(?:', index):
                raise RuleValidationError('REGEX_UNSUPPORTED', 'Use simple groups; flags belong in the ignore-case option.')
            groups.append(False)
            if len(groups) > 17:
                raise RuleValidationError('REGEX_COMPLEXITY', 'The expression has too many nested groups.')
            previous_repeat = False
            index += 3 if pattern.startswith('(?:', index) else 1
            continue
        if char == ')':
            previous_repeat = groups.pop()
            groups[-1] = groups[-1] or previous_repeat
        elif char in '*+?' or (char == '{' and index + 1 < len(pattern) and pattern[index + 1].isdigit()):
            if previous_repeat:
                raise RuleValidationError('REGEX_NESTED_REPEAT', 'Nested or chained repetition is not supported. Simplify the expression.')
            groups[-1] = True
            previous_repeat = True
            if char == '{':
                index = pattern.index('}', index)
        else:
            previous_repeat = False
        index += 1


def validate_pattern(pattern, ignore_case=False):
    if not isinstance(pattern, str) or not 1 <= len(pattern) <= PATTERN_LIMIT:
        raise RuleValidationError('REGEX_LENGTH', 'The expression must contain 1–512 characters.')
    if type(ignore_case) is not bool:
        raise RuleValidationError('REGEX_FLAGS', 'The ignore-case option must be true or false.')
    if any(ord(char) < 32 or ord(char) == 127 for char in pattern):
        raise RuleValidationError('REGEX_CONTROL', 'Use escaped sequences for control characters.')
    try:
        compiled = compile_pattern(pattern, ignore_case)
    except (re2.error, UnicodeError):
        raise RuleValidationError('REGEX_INVALID', 'The expression is invalid or uses syntax unsupported by RE2, such as lookarounds or backreferences.') from None
    _check_repetition(pattern)
    for probe in ['', 'a', ' ', 'a b', '\n', 'one@example.com', '123']:
        if any(match.start() == match.end() for match in compiled.finditer(probe)):
            raise RuleValidationError('REGEX_EMPTY_MATCH', 'The expression can match empty text. Require at least one character.')
    return compiled


def apply_cell(value, *, pattern, replacement, ignore_case=False, maximum=CELL_LIMIT):
    """Bounded literal replacement, never interpret replacement as code/backreferences.

    Returns value, matched, match count, changed, problem code. Spark uses the same
    implementation as the local preview. None and unmatched strings stay intact.
    """
    if value is None:
        return None, False, 0, False, ''
    compiled = compile_pattern(pattern, ignore_case)
    pieces, last, length, count = [], 0, 0, 0
    for match in compiled.finditer(value):
        if match.start() == match.end():
            return value, False, 0, False, 'REGEX_EMPTY_MATCH'
        segment = value[last:match.start()]
        length += len(segment) + len(replacement)
        if length > maximum:
            return value, True, count, False, 'OUTPUT_TOO_LARGE'
        pieces.extend([segment, replacement])
        count += 1
        last = match.end()
    if not count:
        return value, False, 0, False, ''
    length += len(value) - last
    if length > maximum:
        return value, True, count, False, 'OUTPUT_TOO_LARGE'
    pieces.append(value[last:])
    result = ''.join(pieces)
    return result, True, count, result != value, ''


def apply_cells(values, *, pattern, replacement, ignore_case=False, maximum=CELL_LIMIT):
    """One Spark UDF invocation per row, preserving selected-column order."""
    return [apply_cell(value, pattern=pattern, replacement=replacement,
                       ignore_case=ignore_case, maximum=maximum) for value in values]

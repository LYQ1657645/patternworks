"""Session/filter-bound keyset pagination, with a UUID tie-breaker."""
import hashlib
import json
from uuid import UUID

from django.core import signing
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware
from rest_framework.exceptions import ValidationError


def history_page(records, owner, resource, options):
    limit = options['limit']
    # The session ID is never encoded in a public cursor. Its binding is part
    # of the private signing salt, as are all filters and the page size.
    scope = json.dumps([resource, owner, {k:v for k,v in options.items() if k != 'cursor'}], sort_keys=True,default=str)
    salt = 'history-v1:' + hashlib.sha256(scope.encode()).hexdigest()
    if options['cursor']:
        try:
            stamp, identifier = signing.loads(options['cursor'], salt=salt, max_age=86400)
            boundary, identifier = parse_datetime(stamp), UUID(identifier)
            if boundary is None or not is_aware(boundary):
                raise ValueError()
        except (signing.BadSignature, ValueError, TypeError, KeyError):
            raise ValidationError({'cursor': ['Invalid or expired cursor. Return to the first page.']}) from None
        records = records.filter(Q(created_at__lt=boundary) | Q(created_at=boundary, pk__lt=identifier))
    entries = list(records.order_by('-created_at', '-pk')[:limit + 1])
    more = len(entries) > limit
    entries = entries[:limit]
    cursor = signing.dumps([entries[-1].created_at.isoformat(), str(entries[-1].pk)], salt=salt) if more else None
    return entries, cursor

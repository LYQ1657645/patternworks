"""Read-only, session-scoped version graph. Edges always follow persisted parents."""
from ..models import Dataset, Job


def version_graph(anchor, owner, limit=200):
    records = Dataset.objects.filter(owner_session=owner).select_related('connection')
    # Pin the selected ancestry so the selected version remains visible even in a large family.
    path, seen, current = [], set(), anchor
    while current and current.pk not in seen:
        seen.add(current.pk); path.append(current)
        if len(path) >= limit:
            break
        current = records.filter(pk=current.parent_id).first() if current.parent_id else None
    root = path[-1]
    roots = records.filter(parent_id__isnull=True, source_key=root.source_key, sheet_name=root.sheet_name)
    if root.connection_id:
        roots = roots.filter(connection__bucket=root.connection.bucket)
    else:
        # Missing provenance is not proof that similarly named documents are identical.
        roots = roots.filter(pk=root.pk)
    members = {row.pk: row for row in reversed(path)}
    truncated = bool(root.parent_id)
    for row in roots.order_by('-created_at', '-pk')[:limit + 1]:
        if row.pk in members: continue
        if len(members) >= limit:
            truncated = True; break
        members[row.pk] = row
    frontier = list(members)
    while frontier:
        children = list(records.filter(parent_id__in=frontier).exclude(pk__in=members)
                        .order_by('-created_at', '-pk')[:limit - len(members) + 1])
        frontier = []
        for row in children:
            if len(members) >= limit:
                truncated = True; break
            members[row.pk] = row; frontier.append(row.pk)
        if truncated and len(members) >= limit: break
    # Failed/cancelled attempts are activity, never completed planets.
    versions = sorted((d for d in members.values() if d.status == Dataset.Status.READY),
                      key=lambda d: (d.created_at, str(d.pk)))
    nodes, edges = graph_records(versions, members, owner)
    return {'nodes': nodes, 'edges': edges, 'truncated': truncated, 'limit': limit,
            'source_name': root.source_key, 'sheet': root.sheet_name}


def graph_records(versions, members, owner):
    visible = {d.pk for d in versions}
    jobs = Job.objects.filter(owner_session=owner, dataset_id__in=visible, status=Job.Status.SUCCESS,
        kind__in=[Job.Kind.IMPORT_DATASET, Job.Kind.REPLACE_TEXT, Job.Kind.APPLY_RULE, Job.Kind.APPLY_TRANSFORM]
    ).select_related('rule', 'transformation').order_by('created_at', 'pk')
    by_dataset = {j.dataset_id: j for j in jobs}
    nodes, edges = [], []
    for i, d in enumerate(versions):
        nodes.append({'id': str(d.pk), 'parent_id': str(d.parent_id) if d.parent_id else None,
            'name': d.source_key, 'sheet': d.sheet_name, 'version': i + 1,
            'created_at': d.created_at, 'rows': d.row_count, 'column_count': len(d.columns),
            'content_hash': d.metadata.get('content_hash'),
            'lifecycle': d.lifecycle, 'status': d.status, 'available': d.lifecycle == Dataset.Lifecycle.ACTIVE and d.status == Dataset.Status.READY,
            'operation': d.metadata.get('operation', 'import' if not d.parent_id else 'transform')})
        if d.status != Dataset.Status.READY or d.parent_id not in visible or members[d.parent_id].status != Dataset.Status.READY: continue
        job = by_dataset.get(d.pk)
        source = members[d.parent_id]
        keys, details, label = [], {}, 'Transformation'
        if job and job.rule_id:
            r = job.rule; keys = r.target_columns; label = 'Regex replacement'
            details = {'instruction': r.instruction, 'pattern': r.pattern, 'replacement': r.replacement,
                       'ignore_case': r.ignore_case}
        elif job and job.transformation_id:
            t = job.transformation; keys = [t.column]
            label = 'Date normalization' if t.kind == 'DATE' else 'Classification'
            details = {'instruction': t.instruction, 'options': t.options}
        elif job and job.kind == Job.Kind.REPLACE_TEXT:
            keys = [job.parameters.get('column', '')]; label = 'Text replacement'
            details = {k: job.parameters.get(k, '') for k in ['find', 'replacement']}
        names = {c['key']: c['name'] for c in source.columns}
        edges.append({'id': str(job.pk) if job else str(d.pk), 'source': str(d.parent_id), 'target': str(d.pk),
            'label': label, 'columns': [names.get(k, k) for k in keys], 'details': details,
            'created_at': job.finished_at if job else d.created_at,
            'changed_rows': d.metadata.get('changed_rows'), 'matched_rows': d.metadata.get('matched_rows'),
            'status_counts': d.metadata.get('status_counts', {}),
            'column_stats': [{'column': names.get(k, k), **v} for k, v in d.metadata.get('column_stats', {}).items()]})
    return nodes, edges


def library_graph(entries, owner):
    """Bounded metadata page across the entire library, with source-family provenance."""
    from uuid import uuid5, NAMESPACE_URL
    members = {d.pk: d for d in entries}
    pending = {d.parent_id for d in entries if d.parent_id} - members.keys()
    incomplete = False
    # Resolve ancestry in batches, solely within this session. Do not infer identity from a filename.
    for _ in range(100):
        if not pending: break
        remaining = 2000 - len(members)
        if remaining <= 0: incomplete = True; break
        ancestors = list(Dataset.objects.filter(owner_session=owner, pk__in=pending)
                         .select_related('connection')[:remaining])
        members.update({d.pk: d for d in ancestors})
        pending = {d.parent_id for d in ancestors if d.parent_id} - members.keys()
    else:
        incomplete = bool(pending)
    versions = sorted(entries, key=lambda d: (d.created_at, str(d.pk)))
    nodes, edges = graph_records(versions, members, owner)
    groups, counters = {}, {}
    visible_ids = {n['id'] for n in nodes}
    for d, node in zip(versions, nodes):
        root, seen = d, set()
        while root.parent_id in members and root.pk not in seen:
            seen.add(root.pk); root = members[root.parent_id]
        if root.connection_id and not root.parent_id:
            bucket = root.connection.bucket
            identity = '\0'.join([bucket, root.source_key, root.sheet_name])
            key = str(uuid5(NAMESPACE_URL, identity))
        else:
            bucket, key = '', str(root.pk)
        groups.setdefault(key, {'id':key, 'name':d.source_key, 'sheet':d.sheet_name, 'bucket':bucket})
        counters[key] = counters.get(key, 0) + 1
        node.update(group_id=key, version=counters[key], parent_outside_view=bool(d.parent_id and str(d.parent_id) not in visible_ids))
    return {'nodes':nodes, 'edges':edges, 'groups':list(groups.values()), 'source_name':'Dataset library',
            'sheet':'', 'truncated':False, 'limit':100, 'ancestry_incomplete':incomplete}

import json
import sqlite3
from processing.services.content_identity import content_digest, row_digest
from processing.services.datasets import build_page_index


def test_content_identity_covers_order_schema_nulls_and_full_text():
    columns = [{'key': 'c0', 'name': 'Email', 'type': 'string'}]
    def identity(values, schema=columns):
        return content_digest(schema, (row_digest(i+1, [value]) for i, value in enumerate(values)))
    assert identity(['a', 'b']) == identity(['a', 'b'])
    assert identity(['a', 'b']) != identity(['b', 'a'])
    assert identity([None]) != identity([''])
    assert identity(['x' * 10000 + 'a']) != identity(['x' * 10000 + 'b'])
    assert identity(['a']) != identity(['a'], [{'key':'c0', 'name':'Other'}])


def test_ingestion_hash_ignores_partition_order_but_not_truncated_content(tmp_path, settings):
    settings.PREVIEW_CELL_CHARACTERS = 3
    columns = [{'key':'c0', 'name':'Text', 'type':'string'}]
    rows = [{'_row_id':2,'c0':'same ending b'}, {'_row_id':1,'c0':'same ending a'}]
    source = tmp_path/'parts';source.mkdir()
    (source/'part-0.json').write_text('\n'.join(json.dumps(row) for row in rows))
    path = tmp_path/'rows.sqlite3'
    assert build_page_index(source, path, columns, lambda *args:None)==2
    with sqlite3.connect(path) as connection:
        actual = connection.execute('SELECT digest FROM content_identity').fetchone()[0]
        assert json.loads(connection.execute('SELECT cells FROM rows LIMIT 1').fetchone()[0])==['sam']
    expected = content_digest(columns, (row_digest(row['_row_id'], [row['c0']]) for row in reversed(rows)))
    assert actual == expected

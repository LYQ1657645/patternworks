"""Read workbook tabs without importing rows or creating a dataset."""
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile
from defusedxml.ElementTree import fromstring

from django.conf import settings

from .datasets import DatasetCancelled, DatasetProblem, download_source


def list_worksheets(connection, key, report=lambda *args: None, *, job=None):
    suffix = Path(key).suffix.lower()
    if suffix not in {'.xlsx', '.xls'}:
        raise DatasetProblem('EXCEL_REQUIRED', 'Choose an Excel file to list worksheets.')
    directory_options = {}
    if job is not None:
        settings.DATASET_ROOT.mkdir(parents=True, exist_ok=True)
        directory_options = {'dir': settings.DATASET_ROOT, 'prefix': f'.import-{job.pk}-{job.attempt_token}-'}
    with TemporaryDirectory(**directory_options) as directory:
        source = Path(directory) / ('source' + suffix)
        report('Downloading workbook to read worksheet names', 15)
        download_source(connection, key, source, report)
        report('Reading worksheet names', 60)
        workbook = None
        try:
            if suffix == '.xlsx':
                with zipfile.ZipFile(source) as archive:
                    entries = archive.infolist()
                    if len(entries) > 10000 or sum(entry.file_size for entry in entries) > settings.MAX_EXCEL_EXPANDED_BYTES:
                        raise DatasetProblem('EXCEL_TOO_LARGE', 'The expanded Excel workbook exceeds the import limit.')
                    # Read only tab metadata, never shared strings or cell data in the web worker.
                    root = fromstring(archive.read('xl/workbook.xml'))
                    names = [sheet.attrib['name'] for sheet in root.findall('{*}sheets/{*}sheet')]
            else:
                import xlrd
                workbook = xlrd.open_workbook(source, on_demand=True)
                names = workbook.sheet_names()
            if not names:
                raise DatasetProblem('EXCEL_EMPTY', 'This workbook has no worksheets.')
            report('Worksheet names ready', 90)
            return {'sheet_names': names, 'source_key': key}
        except (DatasetProblem, DatasetCancelled):
            raise
        except Exception:
            raise DatasetProblem('EXCEL_INVALID', 'Cannot read this workbook. Use an unencrypted XLSX or XLS file.') from None
        finally:
            if workbook is not None:
                if suffix == '.xlsx':
                    workbook.close()
                else:
                    workbook.release_resources()

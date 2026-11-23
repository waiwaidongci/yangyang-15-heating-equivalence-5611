import csv
import io
import re
from datetime import timezone


def timestamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def csv_text(columns, rows):
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow([column['label'] for column in columns])
    for row in rows:
        writer.writerow([spreadsheet_cell(row.get(column['key'])) for column in columns])
    return '\ufeff' + buffer.getvalue()


def spreadsheet_cell(value):
    if isinstance(value, str) and re.match(r'\s*[=+@-]', value):
        return "'" + value
    return value

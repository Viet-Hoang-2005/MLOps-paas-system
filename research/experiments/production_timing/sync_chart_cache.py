"""Refresh existing numeric chart caches from their original embedded worksheets."""
import io
import json
import math
import posixpath
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as ET

BASE = Path(__file__).resolve().parent
NS = {
    'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
}


def target_path(part, target):
    if target.startswith('/'):
        return target.lstrip('/')
    return posixpath.normpath(posixpath.join(posixpath.dirname(part), target))


def relationships(package, part):
    name = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
    return {row.get('Id'): target_path(part, row.get('Target'))
            for row in ET.fromstring(package.read(name))}


def main():
    candidate = BASE / '.build/candidate.pptx'
    with ZipFile(candidate) as package:
        data = {name: package.read(name) for name in package.namelist()}
        updated = []
        for name in data:
            if not re.fullmatch(r'ppt/charts/chart\d+\.xml', name):
                continue
            root = ET.fromstring(data[name])
            external = root.find('c:externalData', NS)
            workbook_path = relationships(package, name)[external.get(f'{{{NS["r"]}}}id')]
            with ZipFile(io.BytesIO(data[workbook_path])) as workbook:
                sheets = ET.fromstring(workbook.read('xl/workbook.xml'))
                sheet_paths = relationships(workbook, 'xl/workbook.xml')
                cells_by_sheet = {}
                for sheet in sheets.findall('x:sheets/x:sheet', NS):
                    part = sheet_paths[sheet.get(f'{{{NS["r"]}}}id')]
                    rows = ET.fromstring(workbook.read(part))
                    cells_by_sheet[sheet.get('name')] = {
                        cell.get('r'): cell.find('x:v', NS).text
                        for cell in rows.findall('.//x:c', NS) if cell.find('x:v', NS) is not None
                    }
                changes = 0
                max_delta = 0
                for reference in root.findall('.//c:numRef', NS):
                    formula = reference.find('c:f', NS).text
                    match = re.fullmatch(r"(?:'([^']+)'|([^!]+))!\$([A-Z]+)\$(\d+):\$([A-Z]+)\$(\d+)", formula)
                    if not match:
                        raise ValueError(f'Unsupported existing chart range: {formula}')
                    quoted, plain, column, first, last_column, last = match.groups()
                    if column != last_column:
                        raise ValueError('Expected an existing vertical data range')
                    cells = cells_by_sheet[quoted or plain]
                    for point in reference.findall('c:numCache/c:pt', NS):
                        value = point.find('c:v', NS)
                        cell = f'{column}{int(first) + int(point.get("idx"))}'
                        new = cells[cell]
                        old = value.text
                        delta = abs(float(new) - float(old))
                        if not math.isclose(float(new), float(old), rel_tol=0, abs_tol=1e-12):
                            raise ValueError('An existing cache differs materially from its worksheet')
                        if f'{float(new):.6f}' != f'{float(old):.6f}':
                            raise ValueError('Cache refresh would change a displayed six-decimal result')
                        if new != old:
                            value.text = new
                            changes += 1
                            max_delta = max(max_delta, delta)
                if changes:
                    data[name] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                    updated.append({'part': name, 'cache_points_refreshed': changes, 'maximum_float_delta': max_delta})
    output = BASE / '.build/cache-synchronized.pptx'
    with ZipFile(output, 'w', ZIP_DEFLATED) as package:
        for name, content in data.items():
            package.writestr(name, content)
    (BASE / '.build/chart-cache-repair.json').write_text(json.dumps({
        'workbooks_and_formulas_unchanged': True, 'six_decimal_display_values_unchanged': True,
        'changes': updated,
    }, indent=2))
    print('Synchronized', len(updated), 'chart caches with their existing embedded worksheets')


if __name__ == '__main__':
    main()

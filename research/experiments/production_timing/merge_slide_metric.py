"""Merge the Artifact-authored annotation while preserving other source slide parts."""
import copy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as ET

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parent.parent / 'slide/CSONET_2026_Presentation.pptx'
NS = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def text(element):
    return ''.join(node.text or '' for node in element.findall('.//a:t', NS))


def paragraph(value):
    item = ET.Element(f'{{{NS["a"]}}}p')
    run = ET.SubElement(item, f'{{{NS["a"]}}}r')
    ET.SubElement(run, f'{{{NS["a"]}}}t').text = value
    return item


def main():
    annotation = json.loads((BASE / '.build/metric.json').read_text())
    run_name = annotation.get('runName', 'run_20261115')
    summary = json.loads((BASE / 'results' / run_name / 'summary.json').read_text())
    assert summary['complete']
    with ZipFile(SOURCE) as package:
        data = {name: package.read(name) for name in package.namelist()}
    original = data.copy()
    with ZipFile(BASE / '.build/authored-metric.pptx') as package:
        authored = ET.fromstring(package.read('ppt/slides/slide18.xml'))
    metric = next(shape for shape in authored.findall('.//p:sp', NS) if text(shape) == annotation['label'])
    root = ET.fromstring(data['ppt/slides/slide18.xml'])
    max_id = max(int(node.get('id')) for node in root.findall('.//p:cNvPr', NS))
    metric = copy.deepcopy(metric)
    metric.find('p:nvSpPr/p:cNvPr', NS).set('id', str(max_id + 1))
    root.find('p:cSld/p:spTree', NS).append(metric)
    coverage = next(shape for shape in root.findall('.//p:sp', NS) if text(shape).startswith('S1 final coverage'))
    position = coverage.find('p:spPr/a:xfrm/a:off', NS)
    position.set('y', str(int(position.get('y')) - 95250))
    data['ppt/slides/slide18.xml'] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    notes = ET.fromstring(data['ppt/notesSlides/notesSlide18.xml'])
    body = next(shape for shape in notes.findall('.//p:sp', NS)
                if shape.find('p:nvSpPr/p:nvPr/p:ph', NS).get('type') == 'body')
    frame = body.find('p:txBody', NS)
    english = (f"The median inference p95 was {annotation['latency']} milliseconds. "
               f"{annotation['reportCount']} of three windows produced reports, with median availability of "
               f"{annotation['availability']} seconds. We retained {summary['total_client_failures']} client errors across 3,000 requests.")
    vietnamese = ('Bổ sung thời gian vận hành trên cụm triển khai lại. Đo ba lượt S0, '
                  'mỗi lượt 1.000 request, tải mục tiêu 5 request/giây. p95 đo từ máy khách qua HTTPS public. '
                  'Thời gian report tính từ trước request cuối đến khi đọc được JSON và HTML, gồm polling hai giây. '
                  'Đợt đo tháng 11 có provenance riêng với replay tháng 9. Đoạn nói bổ sung khoảng 20 giây. '
                  f"Thời gian report chỉ tổng hợp trên {annotation['reportCount']}/3 cửa sổ hoàn tất. "
                  f"Có {summary['total_client_failures']} lỗi máy khách trong đợt đo này. "
                  'p95 dùng các response thành công, lỗi client được công bố riêng trong báo cáo. '
                  f'Bằng chứng nằm trong research/experiments/production_timing/results/{run_name}/.')
    history = ''
    if run_name != 'run_20261115':
        history = ('These three repeats follow the EC2 restart on 16 November, local time. '
                    'The earlier cohort remains in the artifact with median p95 355 ms, report availability '
                    '44.9 seconds on two of three windows, and one ReadError that left 999 records. '
                    'The cohorts are reported separately.')
        vietnamese += (' Đợt này đo sau khi bật lại EC2 ngày 16/11 theo giờ Việt Nam. '
                       'Đợt trước giữ nguyên với median p95 355 ms, report 44,9 giây trên 2/3 cửa sổ '
                       'và một ReadError khiến chỉ lưu được 999 record. Báo cáo tách riêng hai đợt.')
    frame.append(paragraph('ADDITIONAL ENGLISH SCRIPT (20 seconds)'))
    frame.append(paragraph(english))
    frame.append(paragraph(vietnamese))
    if history:
        frame.append(paragraph('SOURCE AND EARLIER COHORT'))
        frame.append(paragraph(history))
    data['ppt/notesSlides/notesSlide18.xml'] = ET.tostring(notes, encoding='utf-8', xml_declaration=True)
    changed = [name for name in data if data[name] != original[name]]
    assert set(changed) == {'ppt/slides/slide18.xml', 'ppt/notesSlides/notesSlide18.xml'}, changed
    with ZipFile(BASE / '.build/candidate.pptx', 'w', ZIP_DEFLATED) as package:
        for name, content in data.items():
            package.writestr(name, content)
    (BASE / '.build/preservation-check.json').write_text(json.dumps({
        'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'changed_parts': changed, 'other_slides_unchanged': True,
        'original_figures_tables_and_results_preserved': True,
    }, indent=2))
    source_notes = SOURCE.parent / 'CSONET_2026_SPEAKER_NOTES_EN_VI.md'
    notes_copy = source_notes.read_text(encoding='utf-8')
    start = notes_copy.index('## Slide 18 ')
    end = notes_copy.index('## Slide 19 ', start)
    section = notes_copy[start:end] + '\n### Additional production timing\n\n' + english + '\n\n' + vietnamese + '\n\n' + history + '\n\n'
    (BASE / 'output').mkdir(exist_ok=True)
    notes_name = ('CSONET_2026_SPEAKER_NOTES_EN_VI_Post_Restart.md' if history else
                  'CSONET_2026_SPEAKER_NOTES_EN_VI_Production_Benchmark.md')
    (BASE / 'output' / notes_name).write_text(
        notes_copy[:start] + section + notes_copy[end:], encoding='utf-8')
    print('Preserved all source package parts except slide 18 and its notes.')


if __name__ == '__main__':
    main()

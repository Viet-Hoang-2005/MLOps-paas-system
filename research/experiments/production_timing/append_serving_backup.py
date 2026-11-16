"""Append a hidden serving backup to the retained 23-slide conference source."""
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from io import BytesIO

from lxml import etree as ET

BASE = Path(__file__).resolve().parent
SOURCE_COMMIT = '07d1449d'
SOURCE_PATH = 'research/slide/CSONET_2026_Presentation.pptx'
NOTES_PATH = 'research/slide/CSONET_2026_SPEAKER_NOTES_EN_VI.md'
NS = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'


def xml_bytes(root):
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def main():
    source = subprocess.check_output(['git', 'show', f'{SOURCE_COMMIT}:{SOURCE_PATH}'])
    (BASE / '.build/source-before-serving-backup.pptx').write_bytes(source)
    with ZipFile(BytesIO(source)) as package:
        data = {name: package.read(name) for name in package.namelist()}
    original = data.copy()
    content = json.loads((BASE / '.build/serving-backup-content.json').read_text(encoding='utf-8'))
    slide = ET.fromstring(data['ppt/slides/slide23.xml'])
    tree = slide.find('p:cSld/p:spTree', NS)
    for shape in list(tree):
        words = ''.join(node.text or '' for node in shape.findall('.//a:t', NS))
        if words == 'References':
            shape.find('.//a:t', NS).text = content['title']
        elif words == 'A1':
            shape.find('.//a:t', NS).text = content['page']
        elif words and words != 'COMPUTER NETWORKS AND DATA COMMUNICATIONS':
            tree.remove(shape)
    slide.set('show', '0')
    with ZipFile(BASE / '.build/authored-serving-backup.pptx') as package:
        authored = ET.fromstring(package.read('ppt/slides/slide1.xml'))
    additions = [copy.deepcopy(node) for node in authored.find('p:cSld/p:spTree', NS)
                 if ET.QName(node).localname not in ('nvGrpSpPr', 'grpSpPr')]
    next_id = max(int(node.get('id')) for node in tree.findall('.//p:cNvPr', NS)) + 1
    id_map = {}
    for node in additions:
        for identity in node.findall('.//p:cNvPr', NS):
            id_map[identity.get('id')] = str(next_id)
            identity.set('id', str(next_id))
            next_id += 1
    for node in additions:
        for link in node.findall('.//a:stCxn', NS) + node.findall('.//a:endCxn', NS):
            link.set('id', id_map[link.get('id')])
        tree.append(node)
    data['ppt/slides/slide24.xml'] = xml_bytes(slide)

    relationships = ET.fromstring(data['ppt/slides/_rels/slide23.xml.rels'])
    for row in relationships:
        if row.get('Type').endswith('/notesSlide'):
            row.set('Target', '../notesSlides/notesSlide24.xml')
    data['ppt/slides/_rels/slide24.xml.rels'] = xml_bytes(relationships)
    notes = ET.fromstring(data['ppt/notesSlides/notesSlide23.xml'])
    for shape in notes.findall('.//p:sp', NS):
        placeholder = shape.find('p:nvSpPr/p:nvPr/p:ph', NS)
        if placeholder is None:
            continue
        if placeholder.get('type') == 'sldNum':
            for text in shape.findall('.//a:t', NS):
                text.text = '24'
        if placeholder.get('type') != 'body':
            continue
        body = shape.find('p:txBody', NS)
        for paragraph in list(body.findall('a:p', NS)):
            body.remove(paragraph)
        for value in ['ENGLISH SCRIPT', content['english'], 'GIẢI THÍCH TIẾNG VIỆT',
                      content['vietnamese'], 'SOURCES'] + content['sources']:
            paragraph = ET.SubElement(body, f'{{{NS["a"]}}}p')
            run = ET.SubElement(paragraph, f'{{{NS["a"]}}}r')
            ET.SubElement(run, f'{{{NS["a"]}}}t').text = value
    data['ppt/notesSlides/notesSlide24.xml'] = xml_bytes(notes)
    relationships = ET.fromstring(data['ppt/notesSlides/_rels/notesSlide23.xml.rels'])
    for row in relationships:
        if row.get('Type').endswith('/slide'):
            row.set('Target', '../slides/slide24.xml')
    data['ppt/notesSlides/_rels/notesSlide24.xml.rels'] = xml_bytes(relationships)

    presentation = ET.fromstring(data['ppt/presentation.xml'])
    relationships = ET.fromstring(data['ppt/_rels/presentation.xml.rels'])
    next_rel = max(int(row.get('Id')[3:]) for row in relationships if row.get('Id').startswith('rId')) + 1
    ET.SubElement(relationships, f'{{{REL}}}Relationship', Id=f'rId{next_rel}',
                  Type=f'{NS["r"]}/slide', Target='slides/slide24.xml')
    slides = presentation.find('p:sldIdLst', NS)
    assert len(slides) == 23
    ET.SubElement(slides, f'{{{NS["p"]}}}sldId', id=str(max(int(row.get('id')) for row in slides) + 1),
                  attrib={f'{{{NS["r"]}}}id': f'rId{next_rel}'})
    data['ppt/presentation.xml'] = xml_bytes(presentation)
    data['ppt/_rels/presentation.xml.rels'] = xml_bytes(relationships)
    types = ET.fromstring(data['[Content_Types].xml'])
    for old, new in [('/ppt/slides/slide23.xml', '/ppt/slides/slide24.xml'),
                     ('/ppt/notesSlides/notesSlide23.xml', '/ppt/notesSlides/notesSlide24.xml')]:
        row = next(row for row in types if row.get('PartName') == old)
        ET.SubElement(types, f'{{{CT}}}Override', PartName=new, ContentType=row.get('ContentType'))
    data['[Content_Types].xml'] = xml_bytes(types)
    app = ET.fromstring(data['docProps/app.xml'])
    for node in app:
        if ET.QName(node).localname == 'Slides':
            node.text = '24'
    data['docProps/app.xml'] = xml_bytes(app)
    for number in range(1, 24):
        for name in [f'ppt/slides/slide{number}.xml', f'ppt/notesSlides/notesSlide{number}.xml']:
            assert data[name] == original[name], name
    with ZipFile(BASE / '.build/candidate.pptx', 'w', ZIP_DEFLATED) as package:
        for name, value in data.items():
            package.writestr(name, value)
    notes_text = subprocess.check_output(['git', 'show', f'{SOURCE_COMMIT}:{NOTES_PATH}']).decode('utf-8')
    notes_text += ('\n\n## Slide 24 — Serving Workflow Benchmark (backup, A2)\n\n'
                   '### English script\n\n' + content['english'] + '\n\n### Diễn giải tiếng Việt\n\n' +
                   content['vietnamese'] + '\n\n### Sources\n\n' + '\n'.join(content['sources']) + '\n')
    (BASE / 'output/CSONET_2026_SPEAKER_NOTES_EN_VI_Serving_Backup.md').write_text(notes_text, encoding='utf-8')
    (BASE / '.build/serving-backup-preservation.json').write_text(json.dumps({
        'source_commit': SOURCE_COMMIT, 'source_sha256': hashlib.sha256(source).hexdigest(),
        'original_23_slides_and_notes_unchanged': True, 'slide18_restored': True,
        'backup_position': 24, 'after_references': True, 'backup_hidden': True,
    }, indent=2))
    print('Appended hidden backup A2 after References and preserved original slides 1–23.')


if __name__ == '__main__':
    main()

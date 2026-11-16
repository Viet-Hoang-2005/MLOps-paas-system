import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const base = path.dirname(fileURLToPath(import.meta.url));
const modules = process.env.RUNTIME_NODE_MODULES || 'C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1112-737-0_26.1112.737.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules';
const { Presentation, PresentationFile } = await import(pathToFileURL(modules + '/@oai/artifact-tool/dist/artifact_tool.mjs'));
const run = 'run_20261116_postrestart';
const summary = JSON.parse(await fs.readFile(path.join(base, 'results', run, 'summary.json'), 'utf8'));
if (!summary.complete || summary.repeats.length !== 3 || summary.complete_windows !== 3) {
  throw new Error('Three complete, audited repeats are required');
}
const attempts = summary.repeats.reduce((total, row) => total + row.attempts, 0);
const responses = summary.repeats.reduce((total, row) => total + row.valid_responses, 0);
if (attempts !== 3000 || responses !== 3000 || summary.total_client_failures !== 0) {
  throw new Error('Serving response counts differ from the retained measurement');
}
const latency = summary.median_inference_p95_ms.toFixed(0);
const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const slide = presentation.slides.add();
const blue = '#1E4D97';
const dark = '#20324D';

function text(name, value, left, top, width, height, size, color = dark, bold = false) {
  const shape = slide.shapes.add({
    name, geometry: 'textbox', position: { left, top, width, height },
    fill: 'none', line: { fill: 'none', width: 0 },
  });
  shape.text = value;
  shape.text.style = {
    typeface: 'Arial', fontSize: size, color, bold,
    alignment: 'center', verticalAlignment: 'middle', autoFit: 'none', insets: 0,
  };
  return shape;
}

const labels = ['HTTPS client', 'Public ingress', 'JWT gateway', 'XGBoost worker'];
const nodes = labels.map((label, index) => {
  const shape = slide.shapes.add({
    name: label, geometry: 'rect',
    position: { left: 55 + 310 * index, top: 135, width: 240, height: 70 },
    fill: '#EDF3F8', line: { fill: blue, width: 1.5 },
  });
  shape.text = label;
  shape.text.style = {
    typeface: 'Arial', fontSize: 23, color: blue, bold: true,
    alignment: 'center', verticalAlignment: 'middle', autoFit: 'none', insets: 4,
  };
  return shape;
});
for (let index = 0; index < nodes.length - 1; index++) {
  slide.shapes.connect(nodes[index], nodes[index + 1], {
    kind: 'straight', fromSide: 'right', toSide: 'left',
    line: { style: 'solid', fill: blue, width: 2 },
    tail: { type: 'triangle', width: 'med', length: 'med' },
  });
}
text('Latency definition', 'Client-observed round-trip over public HTTPS, including the complete response body.',
  55, 218, 1170, 28, 19, '#52647C');
text('Median inference p95 value', `${latency} ms`, 55, 264, 565, 76, 62, blue, true);
text('Median inference p95 label', 'Median inference p95', 55, 341, 565, 33, 25, blue, true);
text('Valid response count', `${responses.toLocaleString('en-US')} / ${attempts.toLocaleString('en-US')}`,
  660, 264, 565, 76, 62, blue, true);
text('Valid responses label', 'Valid responses', 660, 341, 565, 33, 25, blue, true);

const values = [['Repeat', 'Valid responses', 'Inference p95 (ms)'], ...summary.repeats.map(row => [
  String(row.repeat), `${row.valid_responses.toLocaleString('en-US')} / ${row.attempts.toLocaleString('en-US')}`,
  row.inference_p95_ms.toFixed(2),
])];
const table = slide.tables.add({
  rows: 4, columns: 3, left: 185, top: 399, width: 910, height: 160,
  columnWidths: [210, 350, 350], values,
});
table.borders.assign({ style: 'solid', fill: '#8FA5B9', width: 1 });
for (let row = 0; row < 4; row++) {
  table.rows[row].height = 40;
  for (let column = 0; column < 3; column++) {
    const cell = table.getCell(row, column);
    cell.fill = row === 0 ? blue : row % 2 === 1 ? '#EDF3F8' : '#FFFFFF';
    cell.text.style = {
      typeface: 'Arial', fontSize: 22, color: row === 0 ? '#FFFFFF' : dark,
      bold: row === 0, alignment: 'center', verticalAlignment: 'middle',
    };
  }
}
text('Measurement conditions', 'Post-restart S0 replay, 16 Nov 2026. One model at 5 requests/s. Three repeats of 1,000 requests.',
  55, 589, 1170, 30, 20, dark);
text('Measurement scope', 'Maximum 10 requests in flight. Fifty warm-up requests excluded. p95 uses successful responses.',
  55, 624, 1170, 26, 18, '#52647C');

const english = `We measured the deployed serving path with three repeats of one thousand S0 requests at five requests per second. All three thousand requests returned valid responses. The median of the per-repeat p95 latencies was ${latency} milliseconds. The timer includes the public network and the complete response body.`;
const vietnamese = 'Slide dự phòng dành cho câu hỏi về workflow serving. Luồng đo đi qua client HTTPS, ingress công khai, gateway xác thực JWT và worker XGBoost. Hai số chính là median của ba p95 và số response hợp lệ. Mỗi lượt có 1.000 request S0 ở tải mục tiêu 5 request/giây, tối đa 10 in flight. Warm-up 50 request được audit và dọn riêng. Các prediction và record đã được đối chiếu baseline đóng băng. Phạm vi đo gồm một classifier và một mức tải. Đợt trước vẫn được giữ với một ReadError và 2.999/3.000 response hợp lệ, median p95 355 ms. Hai đợt có kết quả trình bày riêng.';
await fs.mkdir(path.join(base, '.build'), { recursive: true });
await fs.writeFile(path.join(base, '.build/serving-backup-content.json'), JSON.stringify({
  title: 'Serving Workflow Benchmark', page: 'A2', run, english, vietnamese,
  sources: [
    `research/experiments/production_timing/results/${run}/repeat_summary.csv`,
    `research/experiments/production_timing/results/${run}/independent-verification.json`,
    'research/experiments/production_timing/results/run_20261115/summary.json',
  ],
}, null, 2));
await (await PresentationFile.exportPptx(presentation)).save(path.join(base, '.build/authored-serving-backup.pptx'));
console.log('Authored one editable serving-only backup slide.');
process.exit(0);

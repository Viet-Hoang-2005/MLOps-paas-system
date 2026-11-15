import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const base = path.dirname(fileURLToPath(import.meta.url));
const modules = process.env.RUNTIME_NODE_MODULES || 'C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1112-737-0_26.1112.737.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules';
const { FileBlob, PresentationFile } = await import(pathToFileURL(modules + '/@oai/artifact-tool/dist/artifact_tool.mjs'));
const runName = process.argv[2] || 'run_20261115';
const summary = JSON.parse(await fs.readFile(path.join(base, 'results', runName, 'summary.json'), 'utf8'));
if (!summary.complete || summary.repeats.length !== 3) throw new Error('Three audited repeats are required');
const latency = summary.median_inference_p95_ms.toFixed(0);
if (summary.median_window_to_report_seconds === null) throw new Error('No completed report availability measurement');
const availability = summary.median_window_to_report_seconds.toFixed(1);
const reportCount = summary.report_timing_repeats;
const label = `New S0, 5 req/s. Median inference p95 ${latency} ms. Median report availability ${availability} s (${reportCount}/3 windows). ${summary.total_client_failures} client errors / 3,000 requests.`;
const source = path.resolve(base, '../../slide/CSONET_2026_Presentation.pptx');
const presentation = await PresentationFile.importPptx(await FileBlob.load(source));
const slide = presentation.slides.items[17];
const metric = slide.shapes.add({
  name: 'CSoNet production timing', geometry: 'textbox',
  position: { left: 40, top: 598, width: 1200, height: 25 },
  fill: 'none', line: { fill: 'none', width: 0 },
});
metric.text = label;
metric.text.style = {
  typeface: 'Arial', fontSize: 20, color: '#1E4D97', bold: true,
  alignment: 'center', verticalAlignment: 'middle', autoFit: 'none', insets: 0,
};
await fs.mkdir(base + '/.build', { recursive: true });
await fs.writeFile(base + '/.build/metric.json', JSON.stringify({ label, latency, availability, reportCount, runName, failures: summary.total_client_failures }, null, 2));
await (await PresentationFile.exportPptx(presentation)).save(base + '/.build/authored-metric.pptx');
console.log('Authored one editable timing annotation on slide 18.');
process.exit(0);

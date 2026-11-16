import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';

const base = path.dirname(fileURLToPath(import.meta.url));
const skill = 'C:/Users/Isel/.codex/plugins/cache/openai-primary-runtime/presentations/26.1112.11217/skills/presentations';
const runtime = 'C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1112-737-0_26.1112.737.0_x64__3k8sg7r9htsxt/dependencies';
process.env.RUNTIME_NODE_MODULES = runtime + '/node/node_modules';
const source = path.resolve(base, '../../slide/CSONET_2026_Presentation.pptx');
const outputStem = process.argv[2] || 'CSONET_2026_Presentation_Production_Benchmark';
const totalSlides = Number(process.argv[3] || 23);
const tableSlides = totalSlides === 24 ? [17, 18, 24] : [17, 18];
const { finalizePresentation } = await import(pathToFileURL(skill + '/container_tools/artifact_tool_utils.mjs'));
await finalizePresentation({
  workspaceDir: base,
  candidatePath: base + '/.build/cache-synchronized.pptx',
  finalPath: base + '/output/' + outputStem + '.pptx',
  pythonExecutable: runtime + '/python/python.exe',
  integrityValidatorPath: skill + '/container_tools/inspect_presentation_package_integrity.py',
  layoutValidatorPath: skill + '/container_tools/inspect_presentation_layout_geometry.py',
  explicitTotalSlideCount: totalSlides,
  layoutArgs: ['--expected-slide-size-emu', '12192000,6858000',
    ...tableSlides.flatMap(number => ['--require-native-table-slide', String(number)])],
  requiredNativeTableOwnerSlides: tableSlides,
  requiredNativeChartOwnerSlides: [12, 14, 15, 16, 18],
  nativeChartTargetApplication: 'powerpoint',
  fontPolicy: {
    basis: 'reference', families: ['Arial', 'Roboto'], referencePath: source,
    referenceSha256: createHash('sha256').update(await fs.readFile(source)).digest('hex'),
  },
  verifyArtifactToolImport: true,
  receiptPath: base + '/.build/' + outputStem + '-validation.json',
});
console.log(`Finalized the ${totalSlides}-slide presentation.`);
process.exit(0);

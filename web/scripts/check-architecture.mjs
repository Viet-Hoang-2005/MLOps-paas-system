import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve('src');
const normalize = (value) => value.replaceAll('\\', '/');
const files = [];
const architectureErrors = [];
const allowedRootEntries = new Set(['app', 'assets', 'features', 'shared', 'main.tsx']);

for (const entry of fs.readdirSync(root)) {
  if (!allowedRootEntries.has(entry)) {
    architectureErrors.push(`Unexpected src root entry: ${entry}`);
  }
}

function walk(directory) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) walk(fullPath);
    else if (/\.(?:ts|tsx)$/.test(entry.name)) files.push(fullPath);
  }
}

walk(root);
const modules = new Map(files.map((file) => [normalize(path.relative(root, file)).replace(/\.tsx?$/, ''), file]));
const graph = new Map();

for (const [moduleId, file] of modules) {
  const source = fs.readFileSync(file, 'utf8');
  const dependencies = [];
  const matcher = /(?:from\s+|import\s*\(\s*|import\s+)(['"])([^'"]+)\1/g;
  for (const match of source.matchAll(matcher)) {
    const specifier = match[2];
    if (specifier.startsWith('../')) {
      architectureErrors.push(`${moduleId}: parent-relative import ${specifier}`);
    }
    if (/^@\/(?:components|hooks|lib|pages|types)(?:\/|$)/.test(specifier)) {
      architectureErrors.push(`${moduleId}: legacy root import ${specifier}`);
    }
    let target;
    if (specifier.startsWith('@/')) target = specifier.slice(2);
    else if (specifier.startsWith('./')) target = normalize(path.posix.join(path.posix.dirname(moduleId), specifier));
    else continue;
    const resolved = modules.has(target) ? target : `${target}/index`;
    if (modules.has(resolved)) dependencies.push(resolved);
  }
  graph.set(moduleId, dependencies);
}

const visiting = new Set();
const visited = new Set();
const stack = [];
const cycles = [];

function visit(moduleId) {
  if (visiting.has(moduleId)) {
    const start = stack.indexOf(moduleId);
    cycles.push([...stack.slice(start), moduleId]);
    return;
  }
  if (visited.has(moduleId)) return;
  visiting.add(moduleId);
  stack.push(moduleId);
  for (const dependency of graph.get(moduleId) ?? []) visit(dependency);
  stack.pop();
  visiting.delete(moduleId);
  visited.add(moduleId);
}

for (const moduleId of modules.keys()) visit(moduleId);

if (cycles.length || architectureErrors.length) {
  const messages = [
    ...architectureErrors,
    ...cycles.map((cycle) => `Circular dependency: ${cycle.join(' -> ')}`),
  ];
  console.error(messages.join('\n'));
  process.exitCode = 1;
} else {
  console.log(`Architecture check passed across ${modules.size} TypeScript modules.`);
}

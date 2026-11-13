// @vitest-environment node
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("Frontend Architecture Boundaries", () => {
  const root = path.resolve("src");
  const normalize = (value: string) => value.replaceAll("\\", "/");
  const files: string[] = [];
  const architectureErrors: string[] = [];
  const allowedRootEntries = new Set([
    "app",
    "assets",
    "features",
    "shared",
    "main.tsx",
  ]);

  it("should only contain allowed root entries in src", () => {
    const rootErrors: string[] = [];
    for (const entry of fs.readdirSync(root)) {
      if (!allowedRootEntries.has(entry)) {
        rootErrors.push(`Unexpected src root entry: ${entry}`);
      }
    }
    expect(rootErrors).toEqual([]);
  });

  function walk(directory: string) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const fullPath = path.join(directory, entry.name);
      if (entry.isDirectory()) walk(fullPath);
      else if (
        /\.(?:ts|tsx)$/.test(entry.name) &&
        !/\.test\./.test(entry.name)
      ) {
        files.push(fullPath);
      }
    }
  }

  walk(root);
  const modules = new Map(
    files.map((file) => [
      normalize(path.relative(root, file)).replace(/\.tsx?$/, ""),
      file,
    ]),
  );
  const graph = new Map<string, string[]>();

  for (const [moduleId, file] of modules) {
    const source = fs.readFileSync(file, "utf8");
    const dependencies: string[] = [];
    const matcher = /(?:from\s+|import\s*\(\s*|import\s+)(['"])([^'"]+)\1/g;
    for (const match of source.matchAll(matcher)) {
      const specifier = match[2];
      if (specifier.startsWith("../")) {
        architectureErrors.push(
          `${moduleId}: parent-relative import ${specifier}`,
        );
      }
      if (/^@\/(?:components|hooks|lib|pages|types)(?:\/|$)/.test(specifier)) {
        architectureErrors.push(`${moduleId}: legacy root import ${specifier}`);
      }
      let target: string;
      if (specifier.startsWith("@/")) target = specifier.slice(2);
      else if (specifier.startsWith("./"))
        target = normalize(
          path.posix.join(path.posix.dirname(moduleId), specifier),
        );
      else continue;
      const resolved = modules.has(target) ? target : `${target}/index`;
      if (modules.has(resolved)) dependencies.push(resolved);
    }
    graph.set(moduleId, dependencies);
  }

  it("should not have parent-relative imports or legacy root imports", () => {
    expect(architectureErrors).toEqual([]);
  });

  it("should not contain circular dependencies", () => {
    const visiting = new Set<string>();
    const visited = new Set<string>();
    const stack: string[] = [];
    const cycles: string[][] = [];

    function visit(moduleId: string) {
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

    const cycleMessages = cycles.map(
      (cycle) => `Circular dependency: ${cycle.join(" -> ")}`,
    );
    expect(cycleMessages).toEqual([]);
  });
});

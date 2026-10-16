// @vitest-environment node
import fs from "node:fs";
import path from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

describe("Frontend Design Tokens - Color Palette", () => {
  const sourceRoot = path.resolve("src");
  const tokenFile = path.resolve("src/app/styles/tokens.css");
  const sourceFiles: string[] = [];
  const failures: string[] = [];

  const directPalette =
    /(?:^|[\s"'`])(?:[a-z-]+:)*(?:bg|text(?:-color)?|border|ring|outline|decoration|shadow|accent|caret|divide|fill|stroke|from|via|to|selection)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)(?:-\d{2,3})(?:\/\d+)?(?=$|[\s"'`])/g;
  const directBlackWhite =
    /(?:^|[\s"'`])(?:[a-z-]+:)*(?:bg|text(?:-color)?|border|ring|outline|decoration|shadow|accent|caret|divide|fill|stroke|from|via|to|selection)-(?:black|white)(?:\/\d+)?(?=$|[\s"'`])/g;
  const darkColorUtility =
    /(?:^|[\s"'`])dark:(?:hover:|focus:|active:|disabled:)*(?:bg|text(?:-color)?|border|ring|outline|fill|stroke|from|via|to)-[\w[\]()./%-]+(?=$|[\s"'`])/g;
  const legacySemanticTextColor =
    /\b(?:[a-z-]+:)*text-(?:terminal-(?:foreground|muted|info|success|warning|danger)|foreground(?:-muted|-subtle|-disabled|-inverse)?|muted-foreground|primary(?:-hover|-active|-foreground)?|brand-accent|accent-foreground|info(?:-hover|-active|-foreground)?|success(?:-hover|-active|-foreground)?|warning(?:-hover|-active|-foreground)?|danger(?:-hover|-active|-foreground)?|chart-[1-6]|syntax-(?:keyword|type|variable|property|string|number|comment|function))(?:\/\d+)?\b/g;
  const rawHex = /#[0-9a-fA-F]{3,8}\b/g;
  const functionalColor = /\b(?:rgb|rgba|hsl|hsla)\s*\(/g;

  const visitDirectory = (directory: string) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const absolute = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        visitDirectory(absolute);
      } else if (
        /\.(css|ts|tsx)$/.test(entry.name) &&
        absolute !== tokenFile &&
        !/\.test\./.test(entry.name)
      ) {
        sourceFiles.push(absolute);
      }
    }
  };
  visitDirectory(sourceRoot);

  const lineHasIgnore = (lines: string[], line: number) =>
    [lines[line], lines[line - 1]]
      .filter(Boolean)
      .some((value) => value.includes("color-ignore:"));

  const reportMatches = (
    file: string,
    sourceFile: ts.SourceFile,
    lines: string[],
    node: ts.Node,
    value: string,
  ) => {
    const patterns: Array<[string, RegExp]> = [
      ["direct Tailwind palette", directPalette],
      ["direct black/white utility", directBlackWhite],
      ["dark color utility", darkColorUtility],
      ["legacy semantic text-color utility", legacySemanticTextColor],
      ["hex color", rawHex],
      ["functional color", functionalColor],
    ];
    const start = node.getStart(sourceFile);

    for (const [kind, pattern] of patterns) {
      pattern.lastIndex = 0;
      for (const match of value.matchAll(pattern)) {
        const absolutePosition = start + (match.index ?? 0);
        const location =
          sourceFile.getLineAndCharacterOfPosition(absolutePosition);
        if (lineHasIgnore(lines, location.line)) continue;
        failures.push(
          `${path.relative(process.cwd(), file)}:${location.line + 1}:${location.character + 1} ${kind}: ${JSON.stringify(match[0].trim())}`,
        );
      }
    }
  };

  it("should not use unapproved raw colors, direct Tailwind palettes, or dark utilities", () => {
    for (const file of sourceFiles) {
      const source = fs.readFileSync(file, "utf8");
      const lines = source.split(/\r?\n/);
      const sourceFile = ts.createSourceFile(
        file,
        source,
        ts.ScriptTarget.Latest,
        true,
        file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
      );

      const walk = (node: ts.Node) => {
        if (
          ts.isStringLiteral(node) ||
          ts.isNoSubstitutionTemplateLiteral(node) ||
          ts.isTemplateHead(node) ||
          ts.isTemplateMiddle(node) ||
          ts.isTemplateTail(node) ||
          ts.isJsxText(node)
        ) {
          reportMatches(file, sourceFile, lines, node, node.text);
        }
        ts.forEachChild(node, walk);
      };
      walk(sourceFile);
    }

    expect(failures).toEqual([]);
  });
});


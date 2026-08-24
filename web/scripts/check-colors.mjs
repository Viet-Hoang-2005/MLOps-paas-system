import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const sourceRoot = path.resolve("src");
const tokenFile = path.resolve("src/app/styles/tokens.css");
const sourceFiles = [];
const failures = [];

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

const visitDirectory = (directory) => {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      visitDirectory(absolute);
    } else if (/\.(css|ts|tsx)$/.test(entry.name) && absolute !== tokenFile) {
      sourceFiles.push(absolute);
    }
  }
};
visitDirectory(sourceRoot);

const lineHasIgnore = (lines, line) =>
  [lines[line], lines[line - 1]]
    .filter(Boolean)
    .some((value) => value.includes("color-ignore:"));

const reportMatches = (file, sourceFile, lines, node, value) => {
  const patterns = [
    ["direct Tailwind palette", directPalette],
    ["direct black/white utility", directBlackWhite],
    ["dark color utility", darkColorUtility],
    ["legacy semantic text-color utility", legacySemanticTextColor],
    ["hex color", rawHex],
    ["functional color", functionalColor],
  ];
  const start = node.getStart(sourceFile);
  const baseLocation = sourceFile.getLineAndCharacterOfPosition(start);

  for (const [kind, pattern] of patterns) {
    pattern.lastIndex = 0;
    for (const match of value.matchAll(pattern)) {
      const absolutePosition = start + (match.index ?? 0);
      const location = sourceFile.getLineAndCharacterOfPosition(absolutePosition);
      if (lineHasIgnore(lines, location.line)) continue;
      failures.push(
        `${path.relative(process.cwd(), file)}:${location.line + 1}:${location.character + 1} ${kind}: ${JSON.stringify(match[0].trim())}`,
      );
    }
  }

  // Template literal fragments do not include their delimiters. The base
  // location still gives a useful, stable diagnostic when no match offset is
  // available after TypeScript parsing.
  void baseLocation;
};

const checkTypeScript = (file) => {
  const source = fs.readFileSync(file, "utf8");
  const lines = source.split(/\r?\n/);
  const sourceFile = ts.createSourceFile(
    file,
    source,
    ts.ScriptTarget.Latest,
    true,
    file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );

  const walk = (node) => {
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
};

const checkCss = (file) => {
  const source = fs.readFileSync(file, "utf8");
  const lines = source.split(/\r?\n/);
  const patterns = [
    ["hex color", rawHex],
    ["functional color", functionalColor],
    ["dark color utility", darkColorUtility],
  ];

  lines.forEach((line, index) => {
    if (lineHasIgnore(lines, index)) return;
    for (const [kind, pattern] of patterns) {
      pattern.lastIndex = 0;
      for (const match of line.matchAll(pattern)) {
        failures.push(
          `${path.relative(process.cwd(), file)}:${index + 1}:${(match.index ?? 0) + 1} ${kind}: ${JSON.stringify(match[0].trim())}`,
        );
      }
    }
  });
};

for (const file of sourceFiles) {
  if (file.endsWith(".css")) checkCss(file);
  else checkTypeScript(file);
}

if (failures.length > 0) {
  console.error(
    "Frontend color validation failed. Use `text-color-*` for semantic foreground colors and other semantic tokens from tokens.css, or add a scoped `color-ignore: reason` comment for an approved technical exception.",
  );
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(
  `Color token check passed across ${sourceFiles.length} frontend source files.`,
);

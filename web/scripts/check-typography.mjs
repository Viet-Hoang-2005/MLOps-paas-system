import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const sourceRoot = path.resolve("src");
const tokenFile = path.resolve("src/app/styles/tokens.css");
const sourceFiles = [];
const failures = [];

const rawFontSize =
  /\b(?:[a-z-]+:)*text-(?:xs|sm|base|lg|xl|[2-9]xl|\[[^\]]+\])!?/g;
const legacySemanticTypography =
  /\b(?:[a-z-]+:)*text-(?:display|page-title|section-title|heading|metric|body-lg|body|body-strong|control|caption|caption-strong|overline|code-sm|code-sm-strong|terminal)\b/g;
const rawLineHeight =
  /\b(?:[a-z-]+:)*leading-(?:none|tight|snug|normal|relaxed|loose|\d+|\[[^\]]+\])!?/g;
const rawLetterSpacing =
  /\b(?:[a-z-]+:)*tracking-(?:tighter|tight|normal|wide|wider|widest|\[[^\]]+\])!?/g;
const unsupportedWeight =
  /\b(?:[a-z-]+:)*font-(?:thin|extralight|light|extrabold|black|\[[^\]]+\])!?/g;
const inlineTypographyProperties = new Set([
  "fontSize",
  "lineHeight",
  "fontFamily",
  "fontWeight",
  "letterSpacing",
]);

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
    .some((value) => value.includes("typography-ignore:"));

const reportClassTokens = (file, sourceFile, lines, node, value) => {
  const patterns = [
    ["raw font-size utility", rawFontSize],
    ["legacy semantic typography utility", legacySemanticTypography],
    ["raw line-height utility", rawLineHeight],
    ["raw letter-spacing utility", rawLetterSpacing],
    ["unsupported font-weight utility", unsupportedWeight],
  ];
  const start = node.getStart(sourceFile);

  for (const [kind, pattern] of patterns) {
    pattern.lastIndex = 0;
    for (const match of value.matchAll(pattern)) {
      const position = start + (match.index ?? 0);
      const location = sourceFile.getLineAndCharacterOfPosition(position);
      if (lineHasIgnore(lines, location.line)) continue;
      failures.push(
        `${path.relative(process.cwd(), file)}:${location.line + 1}:${location.character + 1} ${kind}: ${JSON.stringify(match[0])}`,
      );
    }
  }
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
      reportClassTokens(file, sourceFile, lines, node, node.text);
    }

    if (
      ts.isPropertyAssignment(node) &&
      inlineTypographyProperties.has(
        node.name.getText(sourceFile).replaceAll(/['"]/g, ""),
      )
    ) {
      const location = sourceFile.getLineAndCharacterOfPosition(
        node.getStart(sourceFile),
      );
      if (!lineHasIgnore(lines, location.line)) {
        failures.push(
          `${path.relative(process.cwd(), file)}:${location.line + 1}:${location.character + 1} inline typography property is not allowed`,
        );
      }
    }

    ts.forEachChild(node, walk);
  };
  walk(sourceFile);
};

const checkCss = (file) => {
  const source = fs.readFileSync(file, "utf8");
  const lines = source.split(/\r?\n/);
  const propertyPattern =
    /\b(font-size|line-height|font-family|font-weight|letter-spacing)\s*:\s*([^;]+);?/;

  lines.forEach((line, index) => {
    if (lineHasIgnore(lines, index)) return;
    const match = line.match(propertyPattern);
    if (!match) return;
    const value = match[2].trim();
    if (
      file.endsWith("globals.css") &&
      /^var\(--(?:font-family|typography)-/.test(value)
    ) {
      return;
    }
    failures.push(
      `${path.relative(process.cwd(), file)}:${index + 1}:${(match.index ?? 0) + 1} raw CSS typography property: ${JSON.stringify(match[0])}`,
    );
  });
};

for (const file of sourceFiles) {
  if (file.endsWith(".css")) checkCss(file);
  else checkTypeScript(file);
}

if (failures.length > 0) {
  console.error(
    "Frontend typography validation failed. Use `text-style-*` semantic typography utilities from tokens.css or add a scoped `typography-ignore: reason` comment for an approved technical exception.",
  );
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(
  `Typography token check passed across ${sourceFiles.length} frontend source files.`,
);

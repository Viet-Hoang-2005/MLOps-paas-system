import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const sourceRoot = path.resolve("src");
const tokenFile = path.resolve("src/app/styles/tokens.css");
const sourceFiles = [];
const failures = [];

const radiusToken =
  /\b(?:[a-z-]+:)*rounded(?:-[A-Za-z0-9_[\].()%!-]+)*/g;
const allowedRadius =
  /^rounded-(?:compact|surface|control|overlay|full|none)!?$/;
const allowedDirectionalRadius =
  /^rounded-(?:t|r|b|l|s|e|ss|se|ee|es)-(?:compact|surface|control|overlay)!?$/;

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
    .some((value) => value.includes("radius-ignore:"));

const normalizeVariant = (token) => token.slice(token.lastIndexOf(":") + 1);

const checkRadiusTokens = (file, sourceFile, lines, node, value) => {
  const start = node.getStart(sourceFile);
  radiusToken.lastIndex = 0;

  for (const match of value.matchAll(radiusToken)) {
    const token = normalizeVariant(match[0]);
    if (allowedRadius.test(token) || allowedDirectionalRadius.test(token)) {
      continue;
    }

    const absolutePosition = start + (match.index ?? 0);
    const location =
      sourceFile.getLineAndCharacterOfPosition(absolutePosition);
    if (lineHasIgnore(lines, location.line)) continue;
    failures.push(
      `${path.relative(process.cwd(), file)}:${location.line + 1}:${location.character + 1} non-semantic radius utility: ${JSON.stringify(match[0])}`,
    );
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
      checkRadiusTokens(file, sourceFile, lines, node, node.text);
    }

    if (
      (ts.isPropertyAssignment(node) || ts.isJsxAttribute(node)) &&
      node.name?.getText(sourceFile).replaceAll(/['"]/g, "") === "borderRadius"
    ) {
      const location = sourceFile.getLineAndCharacterOfPosition(
        node.getStart(sourceFile),
      );
      if (!lineHasIgnore(lines, location.line)) {
        failures.push(
          `${path.relative(process.cwd(), file)}:${location.line + 1}:${location.character + 1} inline borderRadius is not allowed`,
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

  lines.forEach((line, index) => {
    if (lineHasIgnore(lines, index)) return;
    const match = line.match(/\bborder-radius\s*:\s*([^;]+);?/);
    if (
      match &&
      !/^var\(--component-radius-(?:compact|surface|control|overlay|full)\)$/.test(
        match[1].trim(),
      )
    ) {
      failures.push(
        `${path.relative(process.cwd(), file)}:${index + 1}:${(match.index ?? 0) + 1} non-semantic CSS border-radius: ${JSON.stringify(match[1].trim())}`,
      );
    }
  });
};

for (const file of sourceFiles) {
  if (file.endsWith(".css")) checkCss(file);
  else checkTypeScript(file);
}

if (failures.length > 0) {
  console.error(
    "Frontend radius validation failed. Use semantic radius utilities from tokens.css or add a scoped `radius-ignore: reason` comment for an approved graphical exception.",
  );
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(
  `Radius token check passed across ${sourceFiles.length} frontend source files.`,
);

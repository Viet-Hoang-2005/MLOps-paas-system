import ts from "typescript";

export const namespaces = [
  "common",
  "auth",
  "projects",
  "deployments",
  "training",
  "evolution",
  "monitoring",
  "settings",
  "notifications",
  "overview",
] as const;

export type Namespace = (typeof namespaces)[number];

export const resourcePath = (namespace: string, language: string) =>
  namespace === "common"
    ? `src/shared/i18n/${language}.ts`
    : `src/features/${namespace}/i18n/${language}.ts`;

export interface ParsedResourceResult {
  resource: Record<string, unknown> | null;
  errors: string[];
}

export function parseResource(
  source: string,
  file = "resource.ts",
): ParsedResourceResult {
  const ast = ts.createSourceFile(
    file,
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  const diagnostics =
    (ast as unknown as { parseDiagnostics?: ts.Diagnostic[] })
      .parseDiagnostics ?? [];
  const errors: string[] = diagnostics.map((diagnostic) =>
    ts.flattenDiagnosticMessageText(diagnostic.messageText, " "),
  );

  function unwrap(node: ts.Node | undefined): ts.Node | undefined {
    while (
      node &&
      (ts.isAsExpression(node) ||
        ts.isSatisfiesExpression(node) ||
        ts.isParenthesizedExpression(node))
    ) {
      node = node.expression;
    }
    return node;
  }

  function read(
    node: ts.Node | undefined,
    prefix = "",
  ): Record<string, unknown> | string | null {
    node = unwrap(node);
    if (
      node &&
      (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node))
    ) {
      return node.text;
    }
    if (!node || !ts.isObjectLiteralExpression(node)) {
      errors.push(`${prefix}: resource must contain literal objects/strings`);
      return null;
    }
    const result: Record<string, unknown> = {};
    for (const property of node.properties) {
      if (!ts.isPropertyAssignment(property)) {
        errors.push(`${prefix}: computed/spread resources are not allowed`);
        continue;
      }
      const key = property.name.getText(ast).replaceAll(/['"]/g, "");
      if (!key || key in result) {
        errors.push(`${prefix}.${key}: invalid/duplicate key`);
        continue;
      }
      result[key] = read(
        property.initializer,
        prefix ? `${prefix}.${key}` : key,
      );
    }
    return result;
  }

  const exported = ast.statements.filter(
    (statement): statement is ts.VariableStatement =>
      ts.isVariableStatement(statement) &&
      Boolean(
        statement.modifiers?.some(
          (modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword,
        ),
      ),
  );

  if (exported.length !== 1) {
    errors.push("Expected one exported translation object");
  }

  const decl = exported[0]?.declarationList.declarations[0];
  const parsed = read(decl?.initializer);

  return {
    resource:
      parsed && typeof parsed === "object"
        ? (parsed)
        : null,
    errors,
  };
}

const pluralParts = (key: string) =>
  key.match(/^(.*)_(zero|one|two|few|many|other)$/);

const placeholders = (value: string) =>
  [...value.matchAll(/\{\{\s*-?\s*([\w.]+)(?:\s*,[^}]+)?\s*\}\}/g)]
    .map((match) => match[1])
    .sort()
    .join(",");

export function validateResourcePair(
  english: Record<string, unknown> | null,
  vietnamese: Record<string, unknown> | null,
  namespace: string,
): string[] {
  const errors: string[] = [];

  const flatten = (
    object: unknown,
    prefix = "",
    result = new Map<string, string>(),
  ) => {
    if (!object || typeof object !== "object") {
      errors.push(`${namespace}:${prefix}: expected object`);
      return result;
    }
    for (const [key, value] of Object.entries(object)) {
      const full = prefix ? `${prefix}.${key}` : key;
      if (typeof value === "string") {
        if (!value.trim()) {
          errors.push(`${namespace}:${full}: empty translation`);
        }
        result.set(full, value);
      } else {
        flatten(value, full, result);
      }
    }
    return result;
  };

  const en = flatten(english);
  const vi = flatten(vietnamese);

  for (const [language, leaves] of [
    ["en", en],
    ["vi", vi],
  ] as const) {
    const pluralBases = new Set(
      [...leaves.keys()]
        .map(pluralParts)
        .filter((parts): parts is RegExpMatchArray => parts !== null)
        .map((parts) => parts[1]),
    );
    const categories = new Intl.PluralRules(language).resolvedOptions()
      .pluralCategories;
    for (const base of pluralBases) {
      for (const category of categories) {
        if (!leaves.has(`${base}_${category}`)) {
          errors.push(
            `${namespace}/${language}:${base}_${category}: missing locale plural category`,
          );
        }
      }
    }
  }

  // Vietnamese only has the CLDR "other" cardinal category; English has one/other.
  for (const [key, value] of en) {
    const plural = pluralParts(key);
    const target = plural ? `${plural[1]}_other` : key;
    if (!vi.has(target)) {
      errors.push(`${namespace}:${target}: missing Vietnamese key`);
    } else if (placeholders(value) !== placeholders(vi.get(target)!)) {
      errors.push(`${namespace}:${target}: interpolation mismatch`);
    }
  }

  for (const [key, value] of vi) {
    const plural = pluralParts(key);
    if (!en.has(key) && !(plural && en.has(`${plural[1]}_other`))) {
      errors.push(`${namespace}:${key}: unexpected Vietnamese key`);
    }
    const englishValue = en.get(key) ?? (plural && en.get(`${plural[1]}_other`));
    if (
      typeof englishValue === "string" &&
      placeholders(englishValue) !== placeholders(value)
    ) {
      errors.push(`${namespace}:${key}: interpolation mismatch`);
    }
  }

  if (en.size && [...en].every(([key, value]) => vi.get(key) === value)) {
    errors.push(
      `${namespace}: Vietnamese resource is an untranslated English copy`,
    );
  }

  return errors;
}

export function validateRegistration(
  source: string,
  required: readonly string[] = namespaces,
): string[] {
  const ast = ts.createSourceFile(
    "i18n.ts",
    source,
    ts.ScriptTarget.Latest,
    true,
  );
  let resourcesNode: ts.Node | undefined;

  for (const statement of ast.statements) {
    if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        if (declaration.name.getText(ast) === "resources") {
          resourcesNode = declaration.initializer;
          while (
            resourcesNode &&
            (ts.isAsExpression(resourcesNode) ||
              ts.isSatisfiesExpression(resourcesNode))
          ) {
            resourcesNode = resourcesNode.expression;
          }
        }
      }
    }
  }

  const errors: string[] = [];
  const resourcesObj =
    resourcesNode && ts.isObjectLiteralExpression(resourcesNode)
      ? resourcesNode
      : undefined;

  for (const language of ["en", "vi"] as const) {
    const localeProp = resourcesObj?.properties.find(
      (property): property is ts.PropertyAssignment =>
        ts.isPropertyAssignment(property) &&
        property.name.getText(ast).replaceAll(/['"]/g, "") === language,
    );
    const localeInit = localeProp?.initializer;
    const localeObj =
      localeInit && ts.isObjectLiteralExpression(localeInit)
        ? localeInit
        : undefined;

    const keys = new Set(
      localeObj?.properties.map((property) =>
        property.name ? property.name.getText(ast).replaceAll(/['"]/g, "") : "",
      ),
    );

    for (const namespace of required) {
      if (!keys.has(namespace)) {
        errors.push(`${language}:${namespace}: namespace not registered`);
      }
    }
  }

  return errors;
}

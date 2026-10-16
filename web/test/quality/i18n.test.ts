// @vitest-environment node
import fs from "node:fs";
import path from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import {
  parseResource,
  validateRegistration,
  validateResourcePair,
} from "./i18nResources";

describe("Frontend i18n Quality and Completeness", () => {
  const root = path.resolve("src");
  const namespaceFiles = new Map<string, string>([
    ["common", path.join(root, "shared", "i18n", "en.ts")],
    ["auth", path.join(root, "features", "auth", "i18n", "en.ts")],
    ["projects", path.join(root, "features", "projects", "i18n", "en.ts")],
    ["deployments", path.join(root, "features", "deployments", "i18n", "en.ts")],
    ["training", path.join(root, "features", "training", "i18n", "en.ts")],
    ["evolution", path.join(root, "features", "evolution", "i18n", "en.ts")],
    ["monitoring", path.join(root, "features", "monitoring", "i18n", "en.ts")],
    ["settings", path.join(root, "features", "settings", "i18n", "en.ts")],
    [
      "notifications",
      path.join(root, "features", "notifications", "i18n", "en.ts"),
    ],
    ["overview", path.join(root, "features", "overview", "i18n", "en.ts")],
  ]);

  const displayProps = new Set([
    "title",
    "description",
    "subtitle",
    "label",
    "placeholder",
    "aria-label",
    "alt",
    "confirmText",
    "cancelText",
    "emptyText",
  ]);
  const configProps = new Set([...displayProps, "header", "message"]);
  const brands = new Set([
    "ML",
    "drift",
    "AdaptML",
    "Google",
    "GitHub",
    "MLflow",
    "Docker",
    "Kubernetes",
    "Kubeflow",
    "Scikit-learn",
    "XGBoost",
    "PyTorch",
    "TensorFlow",
  ]);

  it("should have complete and valid resource pairs for all namespaces", () => {
    const failures: string[] = [];
    for (const [namespace, file] of namespaceFiles) {
      const en = parseResource(fs.readFileSync(file, "utf8"), file);
      const viFile = file.replace(/en\.ts$/, "vi.ts");
      if (!fs.existsSync(viFile)) {
        failures.push(`${namespace}: missing Vietnamese resource`);
        continue;
      }
      const vi = parseResource(fs.readFileSync(viFile, "utf8"), viFile);
      failures.push(
        ...en.errors.map((error) => `${namespace}/en: ${error}`),
        ...vi.errors.map((error) => `${namespace}/vi: ${error}`),
      );
      failures.push(
        ...validateResourcePair(en.resource, vi.resource, namespace),
      );
    }
    expect(failures).toEqual([]);
  });

  it("should have all namespaces registered in app/i18n.ts", () => {
    const errors = validateRegistration(
      fs.readFileSync(path.join(root, "app", "i18n.ts"), "utf8"),
    );
    expect(errors).toEqual([]);
  });

  it("should contain all required dynamic status keys across locales", () => {
    const dynamicGroups: Record<string, Record<string, string[]>> = {
      evolution: { workspace: ["details", "insights", "metrics", "history"] },
      common: {
        statuses: ["preview", "registered", "running"],
        theme: ["light", "dark", "system"],
        language: ["en", "vi"],
      },
      projects: {
        workflow: [
          "preview",
          "registered",
          "running",
          "pending",
          "queued",
          "building",
          "ready",
          "failed",
          "cancelled",
          "registering",
          "unregistered",
          "deploying",
          "deployFailed",
          "deleting",
          "delete_failed",
        ],
      },
      training: {
        "detail.statuses": [
          "pending",
          "queued",
          "uploading",
          "running",
          "cancelling",
          "completed",
          "failed",
          "cancelled",
        ],
      },
    };

    const failures: string[] = [];
    for (const [namespace, groups] of Object.entries(dynamicGroups)) {
      for (const language of ["en", "vi"]) {
        const file = namespaceFiles
          .get(namespace)!
          .replace(/en\.ts$/, `${language}.ts`);
        if (!fs.existsSync(file)) continue;
        const { resource } = parseResource(fs.readFileSync(file, "utf8"), file);
        for (const [group, keys] of Object.entries(groups)) {
          const node = group
            .split(".")
            .reduce(
              (value: unknown, key: string) =>
                value && typeof value === "object"
                  ? (value as Record<string, unknown>)[key]
                  : undefined,
              resource as unknown,
            );
          for (const key of keys) {
            if (
              !node ||
              typeof (node as Record<string, unknown>)[key] !== "string"
            ) {
              failures.push(
                `${namespace}/${language}:${group}.${key}: missing dynamic status key`,
              );
            }
          }
        }
      }
    }
    expect(failures).toEqual([]);
  });

  it("should not contain hardcoded UI strings in JSX or display props and all t() keys must exist", () => {
    const files: string[] = [];
    const visitDirectory = (directory: string) => {
      for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
        const absolute = path.join(directory, entry.name);
        if (entry.isDirectory()) {
          if (entry.name !== "i18n") visitDirectory(absolute);
        } else if (
          /\.(ts|tsx)$/.test(entry.name) &&
          !/\.test\./.test(entry.name)
        ) {
          files.push(absolute);
        }
      }
    };
    visitDirectory(root);

    const translationKeys = new Map<string, Set<string>>();
    const unwrapExpression = (node: ts.Node): ts.Node => {
      let current = node;
      while (
        ts.isAsExpression(current) ||
        ts.isSatisfiesExpression(current) ||
        ts.isParenthesizedExpression(current)
      ) {
        current = current.expression;
      }
      return current;
    };
    const propertyName = (node: ts.PropertyName): string | null => {
      if (
        ts.isIdentifier(node) ||
        ts.isStringLiteral(node) ||
        ts.isNumericLiteral(node)
      ) {
        return node.text;
      }
      return null;
    };
    const collectResourceKeys = (
      object: ts.ObjectLiteralExpression,
      prefix: string,
      keys: Set<string>,
    ) => {
      for (const property of object.properties) {
        if (
          !ts.isPropertyAssignment(property) &&
          !ts.isShorthandPropertyAssignment(property)
        )
          continue;
        const name = propertyName(property.name);
        if (!name) continue;
        const key = prefix ? `${prefix}.${name}` : name;
        keys.add(key);
        if (
          ts.isPropertyAssignment(property) &&
          ts.isObjectLiteralExpression(property.initializer)
        ) {
          collectResourceKeys(property.initializer, key, keys);
        }
      }
    };

    for (const [namespace, resourceFile] of namespaceFiles) {
      const source = fs.readFileSync(resourceFile, "utf8");
      const sourceFile = ts.createSourceFile(
        resourceFile,
        source,
        ts.ScriptTarget.Latest,
        true,
        ts.ScriptKind.TS,
      );
      const keys = new Set<string>();
      for (const statement of sourceFile.statements) {
        if (!ts.isVariableStatement(statement)) continue;
        for (const declaration of statement.declarationList.declarations) {
          if (declaration.initializer) {
            const initializer = unwrapExpression(declaration.initializer);
            if (ts.isObjectLiteralExpression(initializer)) {
              collectResourceKeys(initializer, "", keys);
            }
          }
        }
      }
      translationKeys.set(namespace, keys);
    }

    const failures: string[] = [];
    const hasIgnoreComment = (sourceFile: ts.SourceFile, node: ts.Node) => {
      const start = sourceFile.getLineAndCharacterOfPosition(
        node.getStart(sourceFile),
      ).line;
      const lines = sourceFile.text.split(/\r?\n/);
      return [lines[start], lines[start - 1]]
        .filter(Boolean)
        .some((line) => line.includes("i18n-ignore:"));
    };

    const isTechnicalLiteral = (value: string) => {
      const text = value.trim();
      if (!/[A-Za-z]/.test(text)) return true;
      if (brands.has(text)) return true;
      if (/^&[A-Za-z]+;$/.test(text)) return true;
      if (/^\d+(?:K|m|h)$/.test(text)) return true;
      if (/^v\d+$/.test(text)) return true;
      if (
        /^(CPU|GPU|RAM|vCPU|API|URL|UUID|ID|HTTP|GET|POST|PUT|PATCH|DELETE)$/i.test(
          text,
        )
      )
        return true;
      if (
        /^(https?:\/\/|\/dashboard\/|\/api\/|[.#][\w-]+|[\w-]+\.(py|csv|json|zip|pkl|joblib|txt|html))/.test(
          text,
        )
      )
        return true;
      if (/^[\w@./:+-]+(?:==|>=|<=|~=|>|<)\d/.test(text)) return true;
      return false;
    };

    const report = (
      sourceFile: ts.SourceFile,
      node: ts.Node,
      value: string,
      kind: string,
    ) => {
      if (isTechnicalLiteral(value) || hasIgnoreComment(sourceFile, node))
        return;
      const location = sourceFile.getLineAndCharacterOfPosition(
        node.getStart(sourceFile),
      );
      failures.push(
        `${path.relative(process.cwd(), sourceFile.fileName)}:${location.line + 1}:${location.character + 1} ${kind}: ${JSON.stringify(value.trim())}`,
      );
    };

    const stringValue = (node: ts.Node): string | null => {
      if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node))
        return node.text;
      return null;
    };

    const isInsideCodeSample = (node: ts.Node) => {
      let current = node.parent;
      while (current) {
        if (
          ts.isJsxElement(current) &&
          ts.isIdentifier(current.openingElement.tagName) &&
          ["code", "pre"].includes(current.openingElement.tagName.text)
        ) {
          return true;
        }
        current = current.parent;
      }
      return false;
    };

    const isRenderedExpressionLiteral = (node: ts.Node) => {
      let current: ts.Node = node;
      while (current.parent && !ts.isJsxExpression(current.parent)) {
        const parent = current.parent;
        if (
          ts.isCallExpression(parent) &&
          ts.isIdentifier(parent.expression) &&
          parent.expression.text === "t"
        ) {
          return false;
        }
        if (ts.isConditionalExpression(parent)) {
          if (current === parent.condition) return false;
          current = parent;
          continue;
        }
        if (ts.isBinaryExpression(parent)) {
          const operator = parent.operatorToken.kind;
          if (
            operator !== ts.SyntaxKind.BarBarToken &&
            operator !== ts.SyntaxKind.QuestionQuestionToken &&
            operator !== ts.SyntaxKind.AmpersandAmpersandToken
          ) {
            return false;
          }
          if (
            operator === ts.SyntaxKind.AmpersandAmpersandToken &&
            current === parent.left
          ) {
            return false;
          }
          current = parent;
          continue;
        }
        if (
          ts.isParenthesizedExpression(parent) ||
          ts.isAsExpression(parent) ||
          ts.isNonNullExpression(parent)
        ) {
          current = parent;
          continue;
        }
        return false;
      }
      return (
        current.parent &&
        ts.isJsxExpression(current.parent) &&
        !ts.isJsxAttribute(current.parent.parent)
      );
    };

    for (const file of files) {
      const source = fs.readFileSync(file, "utf8");
      const sourceFile = ts.createSourceFile(
        file,
        source,
        ts.ScriptTarget.Latest,
        true,
        file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
      );
      const translators = new Map<string, string>();

      const registerTranslator = (node: ts.Node) => {
        if (
          !ts.isVariableDeclaration(node) ||
          !ts.isObjectBindingPattern(node.name) ||
          !node.initializer ||
          !ts.isCallExpression(node.initializer) ||
          !ts.isIdentifier(node.initializer.expression) ||
          node.initializer.expression.text !== "useTranslation"
        ) {
          return;
        }
        const namespaceArgument = node.initializer.arguments[0];
        const namespace =
          namespaceArgument && ts.isStringLiteral(namespaceArgument)
            ? namespaceArgument.text
            : "common";
        for (const element of node.name.elements) {
          const importedName = element.propertyName
            ? propertyName(element.propertyName)
            : ts.isIdentifier(element.name)
              ? element.name.text
              : null;
          if (importedName === "t" && ts.isIdentifier(element.name)) {
            translators.set(element.name.text, namespace);
          }
        }
      };
      const registerWalk = (node: ts.Node) => {
        registerTranslator(node);
        ts.forEachChild(node, registerWalk);
      };
      registerWalk(sourceFile);

      const walk = (node: ts.Node) => {
        if (ts.isJsxText(node) && !isInsideCodeSample(node)) {
          const value = node.text.replace(/\s+/g, " ").trim();
          if (value) report(sourceFile, node, value, "JSX text");
        }

        if (
          (ts.isStringLiteral(node) ||
            ts.isNoSubstitutionTemplateLiteral(node)) &&
          !isInsideCodeSample(node) &&
          isRenderedExpressionLiteral(node)
        ) {
          report(sourceFile, node, node.text, "JSX expression");
        }

        if (ts.isJsxAttribute(node) && ts.isIdentifier(node.name)) {
          const name = node.name.text;
          if (
            displayProps.has(name) &&
            node.initializer &&
            ts.isStringLiteral(node.initializer)
          ) {
            report(sourceFile, node, node.initializer.text, `JSX ${name}`);
          }
        }

        if (
          ts.isCallExpression(node) &&
          ts.isPropertyAccessExpression(node.expression)
        ) {
          const owner = node.expression.expression;
          const method = node.expression.name.text;
          if (
            ts.isIdentifier(owner) &&
            owner.text === "toast" &&
            ["success", "error", "warning", "info"].includes(method)
          ) {
            const value = node.arguments[0]
              ? stringValue(node.arguments[0])
              : null;
            if (value) {
              report(sourceFile, node.arguments[0], value, `toast.${method}`);
            }
          }
        }

        if (
          ts.isCallExpression(node) &&
          ts.isIdentifier(node.expression) &&
          translators.has(node.expression.text) &&
          node.arguments[0] &&
          ts.isStringLiteral(node.arguments[0])
        ) {
          const configuredNamespace = translators.get(node.expression.text)!;
          const rawKey = node.arguments[0].text;
          const separator = rawKey.indexOf(":");
          const namespace =
            separator >= 0 ? rawKey.slice(0, separator) : configuredNamespace;
          const key = separator >= 0 ? rawKey.slice(separator + 1) : rawKey;
          const keys = translationKeys.get(namespace);
          const pluralKeyExists =
            keys &&
            [...keys].some((candidate) => candidate.startsWith(`${key}_`));
          if (!keys || (!keys.has(key) && !pluralKeyExists)) {
            const location = sourceFile.getLineAndCharacterOfPosition(
              node.arguments[0].getStart(sourceFile),
            );
            failures.push(
              `${path.relative(process.cwd(), sourceFile.fileName)}:${location.line + 1}:${location.character + 1} missing i18n key: ${namespace}:${key}`,
            );
          }
        }

        if (
          file.endsWith(".tsx") &&
          ts.isPropertyAssignment(node) &&
          ((ts.isIdentifier(node.name) && configProps.has(node.name.text)) ||
            (ts.isStringLiteral(node.name) && configProps.has(node.name.text)))
        ) {
          const value = stringValue(node.initializer);
          if (value) {
            report(
              sourceFile,
              node.initializer,
              value,
              `UI config ${node.name.getText(sourceFile)}`,
            );
          }
        }

        ts.forEachChild(node, walk);
      };
      walk(sourceFile);
    }

    expect(failures).toEqual([]);
  });
});

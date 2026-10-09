import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import ts from "typescript";

// Transpile real modules in memory using the existing TypeScript/Node tooling.
const modules = new Map();
function moduleURL(file) {
  const key = file.href;
  if (modules.has(key)) return modules.get(key);
  let output = ts.transpileModule(readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  for (const match of [...output.matchAll(/from\s+(["'])([^"']+)\1/g)]) {
    const specifier = match[2];
    let target;
    if (specifier.startsWith("@/") || specifier.startsWith("./")) {
      const base = specifier.startsWith("@/")
        ? new URL(`../src/${specifier.slice(2)}`, import.meta.url)
        : new URL(specifier, file);
      target = moduleURL(
        new URL(
          base.href +
            (existsSync(fileURLToPath(new URL(base.href + ".tsx")))
              ? ".tsx"
              : ".ts"),
        ),
      );
    } else target = import.meta.resolve(specifier);
    output = output.replace(match[0], `from ${JSON.stringify(target)}`);
  }
  const url = `data:text/javascript;base64,${Buffer.from(output).toString("base64")}`;
  modules.set(key, url);
  return url;
}
const load = (path) =>
  import(moduleURL(new URL(`../src/${path}`, import.meta.url)));

const session = await load("shared/api/authSession.ts");
const { queryClient } = await load("shared/api/queryClient.ts");

let checks = 0;
const check = (run) => {
  run();
  checks += 1;
};
const cached = (key) => queryClient.getQueryData(key);

// 1. Signing out removes every cached query.
session.setAuthSession({ access: "token-a", tenantId: "tenant-a" });
queryClient.setQueryData(["profile"], { email: "a@example.com" });
queryClient.setQueryData(["projects", "list"], [{ id: "project-of-a" }]);
check(() => assert.equal(cached(["profile"]).email, "a@example.com"));
session.clearAuthSession();
check(() => assert.equal(cached(["profile"]), undefined));
check(() => assert.equal(cached(["projects", "list"]), undefined));
check(() => assert.equal(queryClient.getQueryCache().getAll().length, 0));

// 2. A silent token refresh for the same tenant keeps the cache.
session.setAuthSession({ access: "token-b1", tenantId: "tenant-b" });
queryClient.setQueryData(["profile"], { email: "b@example.com" });
session.setAuthSession({ access: "token-b2", tenantId: "tenant-b" });
session.setAuthSession({ access: "token-b3" });
check(() => assert.equal(cached(["profile"]).email, "b@example.com"));

// 3. Another account taking over the session (other tab) drops the cache.
session.setAuthSession({ access: "token-c", tenantId: "tenant-c" });
check(() => assert.equal(cached(["profile"]), undefined));

// 4. In-flight requests of the previous user cannot repopulate the cache.
let release;
const slow = queryClient.fetchQuery({
  queryKey: ["slow"],
  queryFn: () => new Promise((resolve) => (release = () => resolve("previous-user-data"))),
});
session.clearAuthSession();
release();
await slow.catch(() => undefined);
check(() => assert.equal(cached(["slow"]), undefined));

// 5. Listener bookkeeping.
let calls = 0;
const stop = session.onAuthSessionReset(() => (calls += 1));
session.clearAuthSession();
stop();
session.clearAuthSession();
check(() => assert.equal(calls, 1));

console.log(`auth cache checks passed (${checks})`);

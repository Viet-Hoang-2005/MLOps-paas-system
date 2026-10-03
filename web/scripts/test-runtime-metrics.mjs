import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const compiled = ts.transpileModule(
  readFileSync(
    new URL("../src/features/projects/realtimeMetrics.ts", import.meta.url),
    "utf8",
  ),
  {
    compilerOptions: { module: ts.ModuleKind.ES2022 },
  },
).outputText;
const { createRealtimeSession } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`
);
const snapshot = (
  timestamp,
  count,
  generation = "first",
  deployment_id = "deployment-1",
) => ({
  mode: "realtime",
  status: "available",
  deployment_id,
  snapshot: {
    timestamp,
    cpu: 0.2,
    memory: 64,
    request_counter: { count, generation },
  },
});
const collect = createRealtimeSession();
assert.equal(collect(snapshot(100, 5)).at(-1).requests, null);
assert.equal(collect(snapshot(105, 15)).at(-1).requests, 2);
assert.equal(collect(snapshot(110, 15)).at(-1).requests, 0);
assert.equal(collect(snapshot(115, 20, "reset")).at(-1).requests, null);
assert.equal(collect(snapshot(120, 1, "reset")).at(-1).requests, null);
const missing = {
  mode: "realtime",
  status: "unavailable",
  deployment_id: "deployment-1",
  snapshot: null,
};
assert.equal(collect(missing, 125).at(-1).cpu, null);
assert.equal(collect(snapshot(130, 30)).at(-1).requests, null);
assert.equal(collect(snapshot(200, 50)).at(-1).requests, null);
assert.equal(collect(snapshot(205, 10, "first", "deployment-2")).length, 1);
assert.equal(collect(snapshot(205, 10, "first", "deployment-2")).length, 1);
const capped = createRealtimeSession();
let result;
for (let i = 0; i < 100; i++) result = capped(snapshot(i * 5, i));
assert.equal(result.length, 60);
result = capped(snapshot(900, 100));
assert.equal(result.length, 1);
assert.equal(createRealtimeSession()(snapshot(100, 5)).length, 1);
console.log("Realtime metrics: 13 cases passed");

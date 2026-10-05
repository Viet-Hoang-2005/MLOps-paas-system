import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import Papa from "papaparse";

async function loadModule(path, jsx = false) {
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  let output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  if (jsx)
    output = output.replaceAll(
      '"react/jsx-runtime"',
      JSON.stringify(import.meta.resolve("react/jsx-runtime")),
    );
  return import(
    `data:text/javascript;base64,${Buffer.from(output).toString("base64")}`
  );
}

const { productionPreview } = await loadModule(
  "../src/features/monitoring/productionPreview.ts",
);
const records = [
  {
    features: { x: 1, label: 'comma, quote"', prediction: "feature collision" },
    prediction: "safe",
  },
  { features: { y: 2, x: null, nested: { score: 1 } }, prediction: "attack" },
];
const unchanged = structuredClone(records);
const result = productionPreview(records);
assert.deepEqual(result.fields, ["x", "label", "y", "nested", "prediction"]);
assert.deepEqual(result.data, [
  ["1", 'comma, quote"', "", "", "safe"],
  ["", "", "2", '{"score":1}', "attack"],
]);
assert.deepEqual(records, unchanged);
assert.deepEqual(Papa.parse(Papa.unparse(result), { header: true }).data, [
  { x: "1", label: 'comma, quote"', y: "", nested: "", prediction: "safe" },
  { x: "", label: "", y: "2", nested: '{"score":1}', prediction: "attack" },
]);
assert.deepEqual(productionPreview([]).data, []);

const { Slider } = await loadModule(
  "../src/shared/components/Slider.tsx",
  true,
);
const options = [500, 1000, 2000, 5000, 10000, 20000].map((value) => ({
  value,
  label: String(value),
}));
const markup = renderToStaticMarkup(
  React.createElement(Slider, {
    options,
    value: 1000,
    onChange() {},
    ariaLabel: "Trigger threshold",
  }),
);
assert.match(markup, /type="range"/);
assert.match(markup, /aria-label="Trigger threshold"/);
assert.match(markup, /aria-valuetext="1000"/);
assert.equal((markup.match(/type="button"/g) ?? []).length, 6);
assert.match(markup, /aria-pressed="true"/);
const disabled = renderToStaticMarkup(
  React.createElement(Slider, {
    options: [options[0]],
    value: 500,
    onChange() {},
    disabled: true,
  }),
);
assert.doesNotMatch(disabled, /NaN|Infinity/);
assert.match(disabled, /disabled=""/);

const hook = readFileSync(
  new URL(
    "../src/features/monitoring/hooks/useDriftMonitoring.ts",
    import.meta.url,
  ),
  "utf8",
);
assert.match(hook, /listProductionData\(modelId!, 100, versionId\)/);
console.log("Monitoring preview/Slider contract: 13 checks passed");

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import axios from "axios";
import ts from "typescript";

const source = ts
  .transpileModule(
    readFileSync(
      new URL("../src/shared/api/inferenceClient.ts", import.meta.url),
      "utf8",
    ),
    { compilerOptions: { module: ts.ModuleKind.ES2022 } },
  )
  .outputText.replace(/^import .*;\s*$/gm, "")
  .replace("export const inferenceClient", "const inferenceClient");

async function scenario(
  statuses,
  details = [],
  initialToken = "access",
  timeout = false,
) {
  let token = initialToken;
  let refreshes = 0;
  const requests = [];
  const client = new Function(
    "axios",
    "getAccessToken",
    "refreshAccessToken",
    `${source}\nreturn inferenceClient;`,
  )(
    axios,
    () => token,
    async () => {
      refreshes++;
      token = "refreshed";
      return token;
    },
  );
  client.defaults.adapter = async (config) => {
    requests.push({ ...config, headers: config.headers.toJSON() });
    assert.equal(config.withCredentials, false);
    assert.equal(config.timeout, 30_000);
    assert.equal(config.headers.Cookie, undefined);
    const index = requests.length - 1;
    const response = {
      config,
      status: statuses[index],
      data: { detail: details[index] },
      headers: {},
      statusText: "",
    };
    if (timeout) throw new axios.AxiosError("timeout", "ECONNABORTED", config);
    if (response.status >= 400)
      throw new axios.AxiosError(
        "gateway error",
        "ERR_BAD_RESPONSE",
        config,
        {},
        response,
      );
    return response;
  };
  await client.post("http://gateway/predict", { data: [[1]] }).catch(() => {});
  return { requests, refreshes, token };
}

assert.equal(
  (await scenario([200], [], null)).requests[0].headers.Authorization,
  undefined,
);
assert.equal(
  (await scenario([200])).requests[0].headers.Authorization,
  "Bearer access",
);
const renewed = await scenario([401, 200], ["Unauthorized: Token has expired"]);
assert.equal(renewed.refreshes, 1);
assert.equal(renewed.requests[1].headers.Authorization, "Bearer refreshed");
assert.equal(
  (
    await scenario(
      [401, 401],
      ["Unauthorized: Token has expired", "Unauthorized: Token has expired"],
    )
  ).refreshes,
  1,
);
for (const code of [401, 403, 500, 504]) {
  const result = await scenario([code], ["Unauthorized: Invalid token"]);
  assert.equal(result.refreshes, 0);
  assert.equal(result.token, "access");
}
const timedOut = await scenario([0], [], "access", true);
assert.equal(timedOut.refreshes, 0);
assert.equal(timedOut.token, "access");
console.log(
  "Inference client: public/private, refresh once, permission errors and timeout passed",
);

import { describe, expect, it } from "vitest";
import { terminalLines } from "./terminalLines";

const progress = (text: string, done = false) =>
  `TERMINAL_PROGRESS ${JSON.stringify({ text, done })}`;

describe("terminal progress rows", () => {
  it("updates the same row and retains final bars for separate downloads", () => {
    expect(
      terminalLines([
        "Collecting package",
        progress("10%"),
        progress("50%"),
        progress("100%", true),
        "Downloading next package",
        progress("20%"),
        progress("100%", true),
        "Installed",
      ]),
    ).toEqual([
      "Collecting package",
      "100%",
      "Downloading next package",
      "100%",
      "Installed",
    ]);
  });
  it("reconstructs an unfinished bar across polling batches", () => {
    const first = ["Installing", progress("10%")];
    expect(terminalLines(first)).toEqual(["Installing", "10%"]);
    expect(terminalLines([...first, progress("30%")])).toEqual([
      "Installing",
      "30%",
    ]);
  });
  it("keeps malformed protocol and ordinary logs as inert text", () => {
    expect(
      terminalLines(["TERMINAL_PROGRESS invalid", "<script>alert(1)</script>"]),
    ).toEqual(["TERMINAL_PROGRESS invalid", "<script>alert(1)</script>"]);
  });
});

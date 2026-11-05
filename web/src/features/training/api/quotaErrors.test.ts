import { describe, expect, it } from "vitest";
import { createTestI18n } from "test/renderWithProviders";
import { getTrainingStartError } from "./quotaErrors";

describe("training quota errors", () => {
  it.each(["en", "vi"] as const)("explains quota exhaustion in %s", (language) => {
    const i18n = createTestI18n(language);
    const error = { isAxiosError: true, response: { data: { error: { code: "training_quota_exceeded", detail: {
      resource: "t4", required_seconds: "7200", remaining_seconds: "0", reset_at: "2026-11-09T00:00:00Z",
    } } } } };
    const message = getTrainingStartError(error, i18n.getFixedT(language, "training"), language);
    expect(message).toContain("NVIDIA T4");
    expect(message).toContain("0s");
    expect(message).toMatch(language === "vi" ? /Không đủ quota/ : /Insufficient/);
  });
});

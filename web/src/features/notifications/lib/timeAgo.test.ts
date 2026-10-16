import { formatTimeAgo } from "@/features/notifications/lib/timeAgo";
import { describe, expect, it } from "vitest";

describe("formatTimeAgo Utility", () => {
  it("should return 'Vừa xong' or 'Just now' for timestamps within 60 seconds", () => {
    const justNow = new Date(Date.now() - 10 * 1000).toISOString();
    expect(formatTimeAgo(justNow, "vi")).toBe("Vừa xong");
    expect(formatTimeAgo(justNow, "en")).toBe("Just now");
  });

  it("should format minutes ago using relative time format", () => {
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatTimeAgo(fiveMinutesAgo, "en")).toBe("5 minutes ago");
    expect(formatTimeAgo(fiveMinutesAgo, "vi")).toMatch(/5 phút trước/);
  });

  it("should format hours ago using relative time format", () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 3600 * 1000).toISOString();
    expect(formatTimeAgo(twoHoursAgo, "en")).toBe("2 hours ago");
    expect(formatTimeAgo(twoHoursAgo, "vi")).toMatch(/2 giờ trước/);
  });

  it("should return raw string on invalid date", () => {
    expect(formatTimeAgo("invalid-iso-string")).toBe("invalid-iso-string");
  });
});


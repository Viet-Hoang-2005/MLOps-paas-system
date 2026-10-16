import {
  detectLanguage,
  LANGUAGE_STORAGE_KEY,
  normalizeLanguage,
  persistLanguage,
} from "@/shared/i18n/language";
import { beforeEach, describe, expect, it } from "vitest";

describe("i18n Language Detection & Synchronization", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.lang = "en";
  });

  it("should normalize valid languages and reject unsupported ones", () => {
    expect(normalizeLanguage("en")).toBe("en");
    expect(normalizeLanguage("en-US")).toBe("en");
    expect(normalizeLanguage("vi")).toBe("vi");
    expect(normalizeLanguage("vi-VN")).toBe("vi");
    expect(normalizeLanguage("fr")).toBeNull();
    expect(normalizeLanguage(null)).toBeNull();
  });

  it("should detect language prioritizing storage over browser preferences", () => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, "vi");
    const lang = detectLanguage(localStorage, ["en-US"]);
    expect(lang).toBe("vi");
  });

  it("should fallback to browser preferences when storage is empty", () => {
    const lang = detectLanguage(localStorage, ["vi-VN", "en"]);
    expect(lang).toBe("vi");
  });

  it("should fallback to 'en' when neither storage nor browser languages match", () => {
    const lang = detectLanguage(localStorage, ["ja-JP", "de"]);
    expect(lang).toBe("en");
  });

  it("should gracefully handle localStorage errors in detectLanguage and persistLanguage", () => {
    const faultyStorage = {
      getItem: () => {
        throw new Error("SecurityError: Access Denied");
      },
      setItem: () => {
        throw new Error("SecurityError: Access Denied");
      },
    };

    expect(() => detectLanguage(faultyStorage, ["en"])).not.toThrow();
    expect(detectLanguage(faultyStorage, ["en"])).toBe("en");
    expect(() => persistLanguage(faultyStorage, "vi")).not.toThrow();
  });
});


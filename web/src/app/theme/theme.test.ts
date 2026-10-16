import {
  applyTheme,
  getStoredTheme,
  getSystemTheme,
  initializeTheme,
  THEME_STORAGE_KEY,
} from "@/app/theme/theme";
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("Theme System & Storage", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "";
    document.documentElement.dataset.theme = "";
  });

  it("should detect system theme from prefers-color-scheme media query", () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("dark"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    expect(getSystemTheme()).toBe("dark");
  });

  it("should get stored theme with fallback to system", () => {
    expect(getStoredTheme()).toBe("system");

    localStorage.setItem(THEME_STORAGE_KEY, "light");
    expect(getStoredTheme()).toBe("light");

    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    expect(getStoredTheme()).toBe("dark");

    localStorage.setItem(THEME_STORAGE_KEY, "invalid-theme");
    expect(getStoredTheme()).toBe("system");
  });

  it("should apply light theme attributes to documentElement", () => {
    const resolved = applyTheme("light");
    expect(resolved).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.style.colorScheme).toBe("light");
  });

  it("should apply dark theme attributes to documentElement", () => {
    const resolved = applyTheme("dark");
    expect(resolved).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("should initialize theme from stored preferences", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    initializeTheme();
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});


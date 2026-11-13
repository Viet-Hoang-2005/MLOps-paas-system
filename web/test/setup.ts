import "@testing-library/jest-dom/vitest";
import "@/app/i18n";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Cleanup DOM, mocks, and browser storage after each test
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  if (typeof window !== "undefined") {
    try {
      window.localStorage.clear();
      window.sessionStorage.clear();
    } catch {
      // Ignore in environments where storage is unavailable
    }
  }
});

// Polyfill window.matchMedia for JSDOM
if (typeof window !== "undefined" && !window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

// Polyfill ResizeObserver for JSDOM
if (typeof window !== "undefined" && !window.ResizeObserver) {
  class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  window.ResizeObserver = ResizeObserverMock;
}

// Polyfill IntersectionObserver for JSDOM
if (typeof window !== "undefined" && !window.IntersectionObserver) {
  class IntersectionObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  window.IntersectionObserver =
    IntersectionObserverMock as unknown as typeof IntersectionObserver;
}

// Polyfill scrollTo
if (typeof window !== "undefined" && !window.scrollTo) {
  window.scrollTo = vi.fn();
}

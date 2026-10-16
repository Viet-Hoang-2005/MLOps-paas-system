import { resources } from "@/app/i18n";
import { ThemeProvider } from "@/app/theme/ThemeProvider";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18next, { type i18n as I18nInstance } from "i18next";
import type { ReactElement, ReactNode } from "react";
import { initReactI18next, I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router-dom";

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export function createTestI18n(language: "en" | "vi" = "en"): I18nInstance {
  const instance = i18next.createInstance();
  void instance.use(initReactI18next).init({
    lng: language,
    fallbackLng: "en",
    resources,
    defaultNS: "common",
    interpolation: { escapeValue: false },
  });
  return instance;
}

export interface RenderWithProvidersOptions
  extends Omit<RenderOptions, "wrapper"> {
  queryClient?: QueryClient;
  i18n?: I18nInstance;
  language?: "en" | "vi";
  initialEntries?: string[];
}

export function renderWithProviders(
  ui: ReactElement,
  options: RenderWithProvidersOptions = {},
) {
  const {
    queryClient = createTestQueryClient(),
    language = "en",
    i18n = createTestI18n(language),
    initialEntries = ["/"],
    ...renderOptions
  } = options;

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <I18nextProvider i18n={i18n}>
          <ThemeProvider>
            <MemoryRouter initialEntries={initialEntries}>
              {children}
            </MemoryRouter>
          </ThemeProvider>
        </I18nextProvider>
      </QueryClientProvider>
    );
  }

  return {
    user: userEvent.setup(),
    queryClient,
    i18n,
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
  };
}


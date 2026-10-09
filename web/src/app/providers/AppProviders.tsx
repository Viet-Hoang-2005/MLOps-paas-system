import { GoogleOAuthProvider } from "@react-oauth/google";
import { QueryClientProvider } from "@tanstack/react-query";
import * as Tooltip from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";
import "@/app/i18n";
import { ThemeProvider } from "@/app/theme/ThemeProvider";
import { queryClient } from "@/shared/api/queryClient";

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <GoogleOAuthProvider
          clientId={import.meta.env.VITE_GOOGLE_CLIENT_ID || ""}
        >
          <Tooltip.Provider delayDuration={250}>{children}</Tooltip.Provider>
        </GoogleOAuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

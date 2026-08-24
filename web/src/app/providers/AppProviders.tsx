import { GoogleOAuthProvider } from '@react-oauth/google';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as Tooltip from '@radix-ui/react-tooltip';
import { type ReactNode, useState } from 'react';
import '@/app/i18n';
import { ThemeProvider } from '@/app/theme/ThemeProvider';

export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5 * 60 * 1000,
            gcTime: 30 * 60 * 1000,
            retry: false,
          },
          mutations: { retry: false },
        },
      }),
  );

  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <GoogleOAuthProvider clientId={import.meta.env.VITE_GOOGLE_CLIENT_ID || ''}>
          <Tooltip.Provider delayDuration={250}>{children}</Tooltip.Provider>
        </GoogleOAuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

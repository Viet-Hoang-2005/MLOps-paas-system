import { QueryClient } from "@tanstack/react-query";
import { onAuthSessionReset } from "@/shared/api/authSession";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 30 * 60 * 1000,
      retry: false,
    },
    mutations: { retry: false },
  },
});

// Cached data belongs to one account: drop it (and any in-flight request) when the
// session ends or the tenant changes, so the next user never sees the previous one's data.
onAuthSessionReset(() => {
  void queryClient.cancelQueries();
  queryClient.clear();
});

import { refreshSession } from "@/features/auth/api/authApi";
import {
  clearAuthStore,
  isAuthenticated,
} from "@/features/auth/authStore";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<
    "checking" | "authenticated" | "unauthenticated"
  >(() => (isAuthenticated() ? "authenticated" : "checking"));

  useEffect(() => {
    if (status !== "checking") {
      return;
    }

    let isMounted = true;

    refreshSession()
      .then(() => {
        if (isMounted) {
          setStatus("authenticated");
        }
      })
      .catch(() => {
        if (isMounted) {
          clearAuthStore();
          setStatus("unauthenticated");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [status]);

  if (status === "checking") {
    return null;
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }

  return children;
}

import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import {
  clearAuthTokens,
  getAccessToken,
  getRefreshToken,
} from "@/features/auth/hooks/useAuth";
import { refreshSession } from "@/features/auth/api/authApi";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<
    "checking" | "authenticated" | "unauthenticated"
  >(() =>
    getAccessToken()
      ? "authenticated"
      : getRefreshToken()
        ? "checking"
        : "unauthenticated",
  );

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
          clearAuthTokens();
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

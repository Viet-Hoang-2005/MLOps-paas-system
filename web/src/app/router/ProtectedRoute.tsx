import { refreshSession } from "@/features/auth/api/authApi";
import { clearAuthStore, isAuthenticated } from "@/features/auth/authStore";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate } from "react-router-dom";
import { isInvalidRefreshSession } from "@/shared/api/authErrors";
import { Button } from "@/shared/components/Button";
import { Placeholder } from "@/shared/components/Placeholder";
import { RouteFallback } from "./RouteFallback";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { t } = useTranslation("auth");
  const [status, setStatus] = useState<
    "checking" | "authenticated" | "unauthenticated" | "unavailable"
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
      .catch((error: unknown) => {
        if (isMounted) {
          if (isInvalidRefreshSession(error)) {
            clearAuthStore();
            setStatus("unauthenticated");
          } else {
            setStatus("unavailable");
          }
        }
      });

    return () => {
      isMounted = false;
    };
  }, [status]);

  if (status === "checking") {
    return <RouteFallback />;
  }

  if (status === "unavailable") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-4 md:p-6">
        <Placeholder
          role="alert"
          title={t("session.unavailableTitle")}
          description={t("session.unavailableDescription")}
          action={
            <Button onClick={() => setStatus("checking")}>
              {t("common:actions.retry")}
            </Button>
          }
        />
      </main>
    );
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }

  return children;
}

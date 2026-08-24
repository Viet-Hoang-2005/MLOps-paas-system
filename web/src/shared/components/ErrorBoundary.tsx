import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "./Button";
import { useTranslation } from "react-i18next";

type ErrorBoundaryProps = {
  children: ReactNode;
};

type ErrorBoundaryState = {
  hasError: boolean;
};

function ErrorFallback() {
  const { t } = useTranslation("common");
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6 text-center text-color-foreground">
      <section className="max-w-md rounded-surface border border-border bg-surface p-8 shadow-[var(--shadow-overlay)]">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-surface bg-danger-subtle text-color-danger">
          <AlertTriangle className="h-6 w-6" />
        </span>
        <h1 className="mt-5 text-style-section-title font-bold text-color-foreground">
          {t("errors.title")}
        </h1>
        <p className="mt-3 text-style-body text-color-muted-foreground">
          {t("errors.description")}
        </p>
        <Button
          icon={<RefreshCw className="h-4 w-4" />}
          onClick={() => window.location.reload()}
          className="mt-6"
        >
          {t("errors.reload")}
        </Button>
      </section>
    </main>
  );
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Unhandled application error", error, errorInfo);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return <ErrorFallback />;
  }
}

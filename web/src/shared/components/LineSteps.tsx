import type { ElementType } from "react";
import { useTranslation } from "react-i18next";

export interface StepItem {
  id: number;
  label: string;
  icon: ElementType;
}

export interface LineStepsProps {
  steps: StepItem[];
  currentStep: number;
  onStepChange?: (step: number) => void;
  isTransitioning?: boolean;
}

export function LineSteps({
  steps,
  currentStep,
  onStepChange,
  isTransitioning = false,
}: LineStepsProps) {
  const { t } = useTranslation("common");
  return (
    <>
      <div className="hidden sm:block rounded-surface border border-border bg-surface px-8 pb-10 pt-6">
        <div className="relative flex items-center justify-between">
          {/* Background line */}
          <div className="absolute left-0 top-5 h-0.5 w-full bg-muted" />
          {/* Active line */}
          <div
            className="absolute left-0 top-5 h-0.5 bg-primary transition-all duration-300"
            style={{
              width: `${((currentStep - 1) / (steps.length - 1)) * 100}%`,
            }}
          />

          {steps.map((item) => {
            const Icon = item.icon;
            const active = currentStep === item.id;
            const done = currentStep > item.id;
            const disabled = isTransitioning || !onStepChange;

            return (
              <div
                key={item.id}
                className="relative z-10 flex flex-col items-center bg-surface px-2"
              >
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onStepChange?.(item.id)}
                  aria-current={active ? "step" : undefined}
                  aria-label={item.label}
                  className={`flex h-10 w-10 items-center justify-center rounded-full border-2 transition-colors ${
                    active
                      ? "border-primary bg-primary text-color-primary-foreground"
                      : done
                        ? "border-primary bg-surface text-color-foreground hover:bg-muted"
                        : "border-border bg-surface text-color-muted-foreground"
                  } ${disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"}`}
                >
                  <Icon className="h-4 w-4" />
                </button>
                <span
                  className={`absolute -bottom-7 whitespace-nowrap text-style-caption-strong ${
                    active
                      ? "text-color-foreground"
                      : done
                        ? "text-color-foreground"
                        : "text-color-muted-foreground"
                  }`}
                >
                  {item.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="sm:hidden overflow-x-auto rounded-surface border border-border bg-surface p-3">
        <span className="sr-only">
          {t("steps.progress", { current: currentStep, total: steps.length })}
        </span>
        <div className="flex min-w-max gap-2">
          {steps.map((item) => {
            const Icon = item.icon;
            const active = currentStep === item.id;
            return (
              <button
                key={item.id}
                type="button"
                disabled={isTransitioning || !onStepChange}
                aria-current={active ? "step" : undefined}
                onClick={() => onStepChange?.(item.id)}
                className={`inline-flex min-h-10 items-center gap-2 rounded-control border px-3 text-style-body-strong focus-visible:ring-2 focus-visible:ring-ring ${active ? "border-primary bg-primary text-color-primary-foreground" : "border-border bg-surface text-color-muted-foreground"} disabled:opacity-60`}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}

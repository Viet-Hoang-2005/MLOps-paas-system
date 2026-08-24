import * as ToastPrimitive from "@radix-ui/react-toast";
import { AlertCircle, CheckCircle2, XCircle, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { setGlobalToastCallback } from "./toastStore";

type ToastType = "success" | "error" | "warning";
interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
}

let nextId = 0;
const visuals = {
  success: { icon: CheckCircle2, className: "text-color-success" },
  error: { icon: XCircle, className: "text-color-danger" },
  warning: { icon: AlertCircle, className: "text-color-warning" },
} as const;

export function ToastContainer() {
  const { t } = useTranslation("common");
  const [items, setItems] = useState<ToastItem[]>([]);
  const addToast = useCallback((type: ToastType, message: string) => {
    setItems((current) => [...current, { id: ++nextId, type, message }]);
  }, []);

  useEffect(() => {
    setGlobalToastCallback(addToast);
    return () => setGlobalToastCallback(null);
  }, [addToast]);

  return (
    <ToastPrimitive.Provider duration={4000} swipeDirection="right">
      {items.map((item) => {
        const visual = visuals[item.type];
        const Icon = visual.icon;
        return (
          <ToastPrimitive.Root
            key={item.id}
            defaultOpen
            onOpenChange={(open) =>
              !open &&
              setItems((current) =>
                current.filter((entry) => entry.id !== item.id),
              )
            }
            className="grid grid-cols-[auto_1fr_auto] items-start gap-3 rounded-surface border border-border bg-surface p-4 text-color-foreground shadow-(--shadow-overlay) data-[state=open]:animate-slide-in"
          >
            <span
              className={`flex h-8 w-8 items-center justify-center ${visual.className}`}
            >
              <Icon className="h-6 w-6" />
            </span>
            <ToastPrimitive.Description className="pt-1.5 text-style-body text-color-foreground">
              {item.message}
            </ToastPrimitive.Description>
            <ToastPrimitive.Close
              className="flex h-8 w-8 items-center justify-center rounded-surface text-color-foreground-subtle hover:bg-surface-hover hover:text-color-foreground active:bg-surface-active"
              aria-label={t("accessibility.dismissNotification")}
            >
              <X className="h-4 w-4" />
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        );
      })}
      <ToastPrimitive.Viewport className="fixed right-4 top-4 z-100 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2 outline-none" />
    </ToastPrimitive.Provider>
  );
}

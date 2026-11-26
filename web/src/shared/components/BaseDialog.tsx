import { cn } from "@/shared/lib/cn";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

export interface BaseDialogProps {
  title: string;
  children: ReactNode;
  onClose: () => void;
  className?: string;
  description?: string;
  onCloseAutoFocus?: (event: Event) => void;
  disabled?: boolean;
  modal?: boolean;
}

export default function BaseDialog({
  title,
  children,
  onClose,
  className,
  description,
  onCloseAutoFocus,
  disabled = false,
  modal = true,
}: BaseDialogProps) {
  const { t } = useTranslation("common");
  return (
    <Dialog.Root
      open
      modal={modal}
      onOpenChange={(open) => {
        if (!open && !disabled) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-overlay animate-fade-in" />
        <Dialog.Content
          onCloseAutoFocus={onCloseAutoFocus}
          onPointerDownOutside={(e) => {
            if (disabled) e.preventDefault();
          }}
          onEscapeKeyDown={(e) => {
            if (disabled) e.preventDefault();
          }}
          className={cn(
            "fixed left-1/2 top-1/2 z-50 flex max-h-[90vh] w-[min(92vw,34rem)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-overlay border border-border bg-surface shadow-(--shadow-overlay) animate-fade-in",
            className,
          )}
        >
          <div className="flex shrink-0 items-start justify-between gap-4 border-b border-border px-5 py-4">
            <div className="space-y-1">
              <Dialog.Title className="text-style-section-title text-color-foreground">
                {title}
              </Dialog.Title>
              {description && (
                <Dialog.Description className="text-style-body text-color-muted-foreground">
                  {description}
                </Dialog.Description>
              )}
            </div>
            <Dialog.Close
              disabled={disabled}
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-surface text-color-foreground-subtle hover:bg-surface-hover hover:text-color-foreground active:bg-surface-active",
                disabled && "cursor-not-allowed opacity-50 pointer-events-none",
              )}
              aria-label={t("accessibility.closeModal")}
            >
              <X className="h-5 w-5" />
            </Dialog.Close>
          </div>
          <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto p-5">
            {children}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

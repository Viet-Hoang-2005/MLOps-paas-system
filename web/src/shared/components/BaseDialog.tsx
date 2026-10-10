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
}

export default function BaseDialog({
  title,
  children,
  onClose,
  className,
  description,
  onCloseAutoFocus,
}: BaseDialogProps) {
  const { t } = useTranslation("common");
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-overlay animate-fade-in" />
        <Dialog.Content
          onCloseAutoFocus={onCloseAutoFocus}
          className={cn(
            "fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[min(92vw,34rem)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto overflow-x-hidden rounded-overlay border border-border bg-surface shadow-(--shadow-overlay) animate-fade-in",
            className,
          )}
        >
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <Dialog.Title className="text-style-section-title text-color-foreground">
              {title}
            </Dialog.Title>
            <Dialog.Close
              className="flex h-9 w-9 items-center justify-center rounded-surface text-color-foreground-subtle hover:bg-surface-hover hover:text-color-foreground active:bg-surface-active"
              aria-label={t("accessibility.closeModal")}
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>
          <div className="p-5">
            {description && (
              <Dialog.Description className="mb-5 text-style-body text-color-muted-foreground">
                {description}
              </Dialog.Description>
            )}
            {children}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

export default function BaseModal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const { t } = useTranslation("common");
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-overlay animate-fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[min(92vw,32rem)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-overlay border border-border bg-surface shadow-(--shadow-overlay) animate-fade-in">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <Dialog.Title className="text-style-heading text-color-foreground">
              {title}
            </Dialog.Title>
            <Dialog.Close
              className="flex h-9 w-9 items-center justify-center rounded-surface text-color-foreground-subtle hover:bg-surface-hover hover:text-color-foreground active:bg-surface-active"
              aria-label={t("accessibility.closeModal")}
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>
          <div className="p-5">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

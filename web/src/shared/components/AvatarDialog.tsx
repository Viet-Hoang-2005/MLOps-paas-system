import { Button } from "@/shared/components/Button";
import { ImageUp, Trash2, X } from "lucide-react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

interface AvatarDialogProps {
  open: boolean;
  busy?: boolean;
  avatarPreview: string;
  onClose: () => void;
  onRemove?: () => void;
  onChange: () => void;
}

export function AvatarDialog({
  open,
  busy = false,
  avatarPreview,
  onClose,
  onRemove,
  onChange,
}: AvatarDialogProps) {
  const { t } = useTranslation("settings");
  if (!open) return null;
  if (typeof document === "undefined") return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay px-4">
      <div className="w-full max-w-lg rounded-surface border border-border bg-surface shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-2">
          <h2 className="text-style-section-title font-bold text-color-foreground">
            {t("avatar")}
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="flex h-8 w-8 items-center justify-center rounded-surface text-color-muted-foreground hover:bg-muted hover:text-color-foreground"
            aria-label={t("avatarDialog.close")}
          >
            <X className="h-6 w-6" />
          </button>
        </div>
        <div className="space-y-6 px-6 py-6">
          {avatarPreview ? (
            <div className="space-y-4">
              <div className="flex justify-center">
                <img
                  src={avatarPreview}
                  alt={t("avatarDialog.current")}
                  className="h-40 w-40 rounded-full object-cover"
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Button
                  type="button"
                  variant="danger"
                  size="md"
                  icon={<Trash2 className="h-4 w-4" />}
                  onClick={onRemove}
                  disabled={busy || !onRemove}
                >
                  {t("removeAvatar")}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="md"
                  icon={<ImageUp className="h-4 w-4" />}
                  onClick={onChange}
                disabled={busy}
                >
                  {t("changeAvatar")}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4 rounded-surface border border-dashed border-border px-5 py-6 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-muted text-color-muted-foreground">
                <ImageUp className="h-6 w-6" />
              </div>
              <div className="space-y-1 pb-1">
                <p className="text-style-heading font-semibold text-color-foreground">
                  {t("avatarDialog.set")}
                </p>
                <p className="text-style-body text-color-muted-foreground">
                  {t("avatarDialog.setDescription")}
                </p>
              </div>
              <Button
                type="button"
                icon={<ImageUp className="h-4 w-4" />}
                onClick={onChange}
                disabled={busy}
              >
                {t("avatarDialog.upload")}
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

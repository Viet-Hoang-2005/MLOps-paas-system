import { ImageUp, Trash2, X } from "lucide-react";
import { Button } from "@/shared/components/Button";
import type { AvatarRecord } from "@/features/settings/types";
import { useTranslation } from "react-i18next";

interface AvatarModalProps {
  open: boolean;
  avatarPreview: string;
  avatarHistory?: AvatarRecord[];
  historyLoading?: boolean;
  selectingAvatarId?: string | null;
  onClose: () => void;
  onRemove?: () => void;
  onChange: () => void;
  onSelectAvatar?: (avatarId: string) => void;
}

export function AvatarModal({
  open,
  avatarPreview,
  avatarHistory = [],
  historyLoading = false,
  selectingAvatarId = null,
  onClose,
  onRemove,
  onChange,
  onSelectAvatar,
}: AvatarModalProps) {
  const { t } = useTranslation("settings");
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay px-4">
      <div className="w-full max-w-lg rounded-surface border border-border bg-surface shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-2">
          <h2 className="text-style-section-title font-bold text-color-foreground">{t("avatar")}</h2>
          <button
            type="button"
            onClick={onClose}
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
                  disabled={!onRemove}
                >
                  {t("removeAvatar")}
                </Button>
                <Button
                  type="button"
                  size="md"
                  icon={<ImageUp className="h-4 w-4" />}
                  onClick={onChange}
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
              >
                {t("avatarDialog.upload")}
              </Button>
            </div>
          )}
          {(historyLoading || avatarHistory.length > 0) && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-style-body-strong text-color-foreground">
                  {t("avatarDialog.previous")}
                </h3>
                {historyLoading && (
                  <span className="text-style-caption-strong text-color-muted-foreground">
                    {t("avatarDialog.loading")}
                  </span>
                )}
              </div>
              <div className="flex gap-3 overflow-x-auto pb-1">
                {avatarHistory.map((avatar) => (
                  <button
                    key={avatar.id}
                    type="button"
                    onClick={() => onSelectAvatar?.(avatar.id)}
                    disabled={
                      avatar.is_current || selectingAvatarId === avatar.id
                    }
                    className={`h-16 w-16 shrink-0 overflow-hidden rounded-full border-2 transition ${
                      avatar.is_current
                        ? "border-primary"
                        : "border-border hover:border-muted-foreground disabled:opacity-60"
                    }`}
                    aria-label={
                      avatar.is_current
                        ? t("avatarDialog.current")
                        : t("avatarDialog.selectPrevious")
                    }
                    title={
                      avatar.is_current
                        ? t("avatarDialog.current")
                        : t("avatarDialog.useThis")
                    }
                  >
                    <img
                      src={avatar.url}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

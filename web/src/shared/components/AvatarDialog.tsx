import BaseDialog from "@/shared/components/BaseDialog";
import { Button } from "@/shared/components/Button";
import { ImageUp, Trash2 } from "lucide-react";
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

  return (
    <BaseDialog
      title={t("avatar")}
      onClose={onClose}
      disabled={busy}
      modal={false}
      className="w-[min(92vw,32rem)]"
    >
      <div className="space-y-6">
        {avatarPreview ? (
          <div className="space-y-6">
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
    </BaseDialog>
  );
}

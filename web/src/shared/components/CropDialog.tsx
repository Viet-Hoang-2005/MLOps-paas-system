import BaseDialog from "@/shared/components/BaseDialog";
import { Button } from "@/shared/components/Button";
import { useState } from "react";
import Cropper, { type Area, type Point } from "react-easy-crop";
import { useTranslation } from "react-i18next";

const createImage = (url: string) =>
  new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.addEventListener("load", () => resolve(image));
    image.addEventListener("error", reject);
    image.src = url;
  });

const getCroppedAvatarFile = async (imageSrc: string, cropPixels: Area) => {
  const image = await createImage(imageSrc);
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");

  if (!context) {
    throw new Error("Unable to create image context.");
  }

  canvas.width = cropPixels.width;
  canvas.height = cropPixels.height;

  context.drawImage(
    image,
    cropPixels.x,
    cropPixels.y,
    cropPixels.width,
    cropPixels.height,
    0,
    0,
    cropPixels.width,
    cropPixels.height,
  );

  return new Promise<File>((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error("Unable to crop avatar."));
          return;
        }
        resolve(
          new File([blob], `avatar-${Date.now()}.jpg`, { type: "image/jpeg" }),
        );
      },
      "image/jpeg",
      0.9,
    );
  });
};

interface CropDialogProps {
  imageSrc: string;
  loading?: boolean;
  onClose: () => void;
  onConfirm: (file: File) => void | Promise<void>;
  onError?: () => void;
}

export function CropDialog({
  imageSrc,
  loading = false,
  onClose,
  onConfirm,
  onError,
}: CropDialogProps) {
  const { t } = useTranslation("settings");
  const [crop, setCrop] = useState<Point>({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState<Area | null>(null);
  const [internalLoading, setInternalLoading] = useState(false);

  if (!imageSrc) return null;

  const isBusy = loading || internalLoading;

  const handleConfirm = async () => {
    if (!croppedAreaPixels) return;

    setInternalLoading(true);
    let croppedFile: File;
    try {
      croppedFile = await getCroppedAvatarFile(imageSrc, croppedAreaPixels);
    } catch {
      onError?.();
      setInternalLoading(false);
      return;
    }

    try {
      await onConfirm(croppedFile);
    } finally {
      setInternalLoading(false);
    }
  };

  return (
    <BaseDialog
      title={t("avatarDialog.crop")}
      onClose={onClose}
      disabled={isBusy}
      className="w-[min(92vw,36rem)]"
    >
      <div className="space-y-5">
        <div className="relative h-72 overflow-hidden rounded-surface bg-terminal">
          <Cropper
            image={imageSrc}
            crop={crop}
            zoom={zoom}
            aspect={1}
            cropShape="round"
            showGrid={false}
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onCropComplete={(_, croppedPixels) =>
              setCroppedAreaPixels(croppedPixels)
            }
          />
        </div>
        <label
          htmlFor="avatar-zoom"
          className="flex flex-col gap-2 text-style-body-strong text-color-foreground"
        >
          {t("avatarDialog.zoom")}
          <input
            id="avatar-zoom"
            type="range"
            min="1"
            max="3"
            step="0.1"
            value={zoom}
            onChange={(event) => setZoom(Number(event.target.value))}
            className="w-full accent-primary"
            disabled={isBusy}
          />
        </label>
        <div className="flex justify-end gap-3">
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={isBusy}
          >
            {t("avatarDialog.cancel")}
          </Button>
          <Button
            type="button"
            loading={isBusy}
            disabled={isBusy}
            onClick={handleConfirm}
          >
            {t("avatarDialog.use")}
          </Button>
        </div>
      </div>
    </BaseDialog>
  );
}

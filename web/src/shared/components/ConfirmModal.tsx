import * as AlertDialog from '@radix-ui/react-alert-dialog';
import { AlertTriangle, Info } from 'lucide-react';
import { useRef, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from './Button';

type ConfirmTone = 'default' | 'danger';

interface ConfirmModalProps {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmText?: string;
  cancelText?: string;
  tone?: ConfirmTone;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmModal({
  open,
  title,
  description,
  confirmText,
  cancelText,
  tone = 'default',
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  const { t } = useTranslation('common');
  const resolvedConfirmText = confirmText || t('actions.confirm');
  const resolvedCancelText = cancelText || t('actions.cancel');
  const danger = tone === 'danger';
  const confirmedRef = useRef(false);
  return (
    <AlertDialog.Root open={open} onOpenChange={(nextOpen) => {
      if (nextOpen) return;
      if (confirmedRef.current) {
        confirmedRef.current = false;
        return;
      }
      onCancel();
    }}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-50 bg-overlay animate-fade-in" />
        <AlertDialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,32rem)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-overlay border border-border bg-surface text-color-foreground shadow-[var(--shadow-overlay)] animate-fade-in">
          <div className="flex items-center gap-3 border-b border-border px-5 py-4">
            <span className={danger ? 'flex h-12 w-12 shrink-0 items-center justify-center rounded-surface bg-danger-subtle text-color-danger' : 'flex h-12 w-12 shrink-0 items-center justify-center rounded-surface bg-muted text-color-foreground'}>
              {danger ? <AlertTriangle className="h-5 w-5" /> : <Info className="h-5 w-5" />}
            </span>
            <AlertDialog.Title className="text-style-heading text-color-foreground">{title}</AlertDialog.Title>
          </div>
          <div className="space-y-8 px-6 py-6">
            <AlertDialog.Description asChild>
              <div className="text-style-body-lg text-color-muted-foreground">{description}</div>
            </AlertDialog.Description>
            <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <AlertDialog.Cancel asChild><Button variant="secondary">{resolvedCancelText}</Button></AlertDialog.Cancel>
              <AlertDialog.Action asChild><Button variant={danger ? 'danger' : 'primary'} loading={loading} onClick={() => { confirmedRef.current = true; onConfirm(); }}>{resolvedConfirmText}</Button></AlertDialog.Action>
            </div>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}

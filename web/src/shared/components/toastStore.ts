type ToastType = 'success' | 'error' | 'warning';

type ToastCallback = (type: ToastType, message: string) => void;

let globalToastCallback: ToastCallback | null = null;

export const setGlobalToastCallback = (callback: ToastCallback | null) => {
  globalToastCallback = callback;
};

const normalizeToastMessage = (message: unknown): string => {
  if (typeof message === 'string') return message;
  if (message instanceof Error) return message.message;
  return 'An unexpected error occurred.';
};

export const toast = {
  success: (message: unknown) => globalToastCallback?.('success', normalizeToastMessage(message)),
  error: (message: unknown) => globalToastCallback?.('error', normalizeToastMessage(message)),
  warning: (message: unknown) => globalToastCallback?.('warning', normalizeToastMessage(message)),
};

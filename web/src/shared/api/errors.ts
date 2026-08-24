import axios from 'axios';

const preferredErrorKeys = ['error', 'detail', 'message'];

const asMessage = (value: unknown, field?: string): string | null => {
  if (typeof value === 'string') {
    const message = value.trim();
    return message ? (field ? `${field}: ${message}` : message) : null;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const message = asMessage(item, field);
      if (message) return message;
    }
    return null;
  }
  if (!value || typeof value !== 'object') return null;
  const data = value as Record<string, unknown>;
  for (const key of preferredErrorKeys) {
    const message = asMessage(data[key]);
    if (message) return message;
  }
  for (const [key, item] of Object.entries(data)) {
    if (key === 'code') continue;
    const message = asMessage(item, key);
    if (message) return message;
  }
  return null;
};

export const getApiErrorMessage = (error: unknown, fallback: string): string => {
  if (!axios.isAxiosError<unknown>(error)) {
    return error instanceof Error ? error.message : fallback;
  }
  const data = error.response?.data;
  if (!data) return error.message || fallback;
  if (typeof data === 'string') return data.trim().startsWith('<') ? fallback : data;
  if (typeof data !== 'object') return error.message || fallback;
  return asMessage(data) || error.message || fallback;
};

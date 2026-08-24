import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { authEn } from '@/features/auth/i18n/en';
import { deployEn } from '@/features/deploy/i18n/en';
import { catalogEn } from '@/features/catalog/i18n/en';
import { driftEn } from '@/features/drift/i18n/en';
import { notificationsEn } from '@/features/notifications/i18n/en';
import { registryEn } from '@/features/registry/i18n/en';
import { settingsEn } from '@/features/settings/i18n/en';
import { trainingEn } from '@/features/training/i18n/en';
import { commonEn } from '@/shared/i18n/en';

const resources = {
  en: {
    common: commonEn,
    auth: authEn,
    catalog: catalogEn,
    deploy: deployEn,
    training: trainingEn,
    registry: registryEn,
    drift: driftEn,
    settings: settingsEn,
    notifications: notificationsEn,
  },
} as const;

void i18n.use(initReactI18next).init({
  resources,
  lng: 'en',
  fallbackLng: 'en',
  defaultNS: 'common',
  interpolation: { escapeValue: false },
});

export default i18n;

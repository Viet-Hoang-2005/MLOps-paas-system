import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { authEn } from "@/features/auth/i18n/en";
import { deployEn } from "@/features/deployments/i18n/en";
import { catalogEn } from "@/features/projects/i18n/en";
import { driftEn } from "@/features/monitoring/i18n/en";
import { notificationsEn } from "@/features/notifications/i18n/en";
import { registryEn } from "@/features/evolution/i18n/en";
import { settingsEn } from "@/features/settings/i18n/en";
import { trainingEn } from "@/features/training/i18n/en";
import { commonEn } from "@/shared/i18n/en";
import { commonVi } from "@/shared/i18n/vi";
import { projectsVi } from "@/features/projects/i18n/vi";
import { monitoringVi } from "@/features/monitoring/i18n/vi";
import { evolutionVi } from "@/features/evolution/i18n/vi";

const resources = {
  vi: {
    common: commonVi,
    projects: projectsVi,
    monitoring: monitoringVi,
    evolution: evolutionVi,
  },
  en: {
    common: commonEn,
    auth: authEn,
    projects: catalogEn,
    deployments: deployEn,
    training: trainingEn,
    evolution: registryEn,
    monitoring: driftEn,
    settings: settingsEn,
    notifications: notificationsEn,
  },
} as const;

void i18n.use(initReactI18next).init({
  resources,
  lng: "en",
  fallbackLng: "en",
  defaultNS: "common",
  interpolation: { escapeValue: false },
});

export default i18n;

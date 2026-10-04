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
import { overviewEn } from "@/features/overview/i18n/en";
import { overviewVi } from "@/features/overview/i18n/vi";
import { authVi } from "@/features/auth/i18n/vi";
import { deploymentsVi } from "@/features/deployments/i18n/vi";
import { trainingVi } from "@/features/training/i18n/vi";
import { settingsVi } from "@/features/settings/i18n/vi";
import { notificationsVi } from "@/features/notifications/i18n/vi";
import {
  detectLanguage,
  normalizeLanguage,
  persistLanguage,
} from "@/shared/i18n/language";

const browserStorage = () => {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
};
const initialLanguage = detectLanguage(
  browserStorage(),
  navigator.languages ?? [navigator.language],
);
document.documentElement.lang = initialLanguage;
i18n.on("languageChanged", (value) => {
  const language = normalizeLanguage(value) ?? "en";
  document.documentElement.lang = language;
  persistLanguage(browserStorage(), language);
});

const resources = {
  vi: {
    auth: authVi,
    deployments: deploymentsVi,
    training: trainingVi,
    settings: settingsVi,
    notifications: notificationsVi,
    common: commonVi,
    projects: projectsVi,
    monitoring: monitoringVi,
    evolution: evolutionVi,
    overview: overviewVi,
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
    overview: overviewEn,
  },
} as const;

void i18n.use(initReactI18next).init({
  initAsync: false,
  resources,
  lng: initialLanguage,
  supportedLngs: ["en", "vi"],
  load: "languageOnly",
  fallbackLng: "en",
  defaultNS: "common",
  interpolation: { escapeValue: false },
});

export default i18n;

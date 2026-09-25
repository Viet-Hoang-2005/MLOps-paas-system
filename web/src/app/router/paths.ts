export const routes = {
  login: "/login",
  dashboard: "/dashboard",
  projects: "/dashboard/projects",
  newProject: "/dashboard/projects/new",
  notifications: "/dashboard/notifications",
  profile: "/dashboard/settings/profile",
  apiTokens: "/dashboard/api-tokens",

  developerSettings: "/dashboard/api-tokens",
} as const;

export const projectRoute = (base: string, projectId: string) =>
  `${base}/${projectId}`;

export const projectPaths = {
  root: (projectId: string) => `/dashboard/projects/${projectId}`,
  overview: (projectId: string) => `/dashboard/projects/${projectId}/overview`,
  overviewPresent: (projectId: string) =>
    `/dashboard/projects/${projectId}/overview/present`,
  overviewDraft: (projectId: string) =>
    `/dashboard/projects/${projectId}/overview/draft`,
  deployment: (projectId: string) =>
    `/dashboard/projects/${projectId}/deployment`,
  playground: (projectId: string) =>
    `/dashboard/projects/${projectId}/deployment/playground`,
  monitoring: (projectId: string) =>
    `/dashboard/projects/${projectId}/monitoring`,
  training: (projectId: string) =>
    `/dashboard/projects/${projectId}/training`,
  trainingJob: (projectId: string, jobId: string) =>
    `/dashboard/projects/${projectId}/training/jobs/${jobId}`,
  evolution: (projectId: string) =>
    `/dashboard/projects/${projectId}/evolution`,
  evolutionVersion: (projectId: string, versionId: string) =>
    `/dashboard/projects/${projectId}/evolution/versions/${versionId}`,
} as const;

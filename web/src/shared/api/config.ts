const normalizeApiBaseURL = (url: string) =>
  url.replace(/\/+$/, "").replace(/\/auth$/, "");

const env =
  typeof import.meta !== "undefined" && import.meta.env
    ? import.meta.env
    : ({} as Record<string, string | undefined>);

export const apiBaseURL = normalizeApiBaseURL(
  env.VITE_API_BASE_URL || "http://localhost:8000/api",
);

const controlPlaneApiBaseURL = normalizeApiBaseURL(
  env.VITE_CONTROL_PLANE_API_BASE_URL || apiBaseURL,
);

export const controlPlaneURL = (path: string) =>
  `${controlPlaneApiBaseURL.replace(/\/+$/, "")}${path}`;

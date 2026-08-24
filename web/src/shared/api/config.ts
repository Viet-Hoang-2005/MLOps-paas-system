const normalizeApiBaseURL = (url: string) => url.replace(/\/+$/, '').replace(/\/auth$/, '');

export const apiBaseURL = normalizeApiBaseURL(
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
);

const controlPlaneApiBaseURL = normalizeApiBaseURL(
  import.meta.env.VITE_CONTROL_PLANE_API_BASE_URL || apiBaseURL,
);

export const controlPlaneURL = (path: string) =>
  `${controlPlaneApiBaseURL.replace(/\/+$/, '')}${path}`;

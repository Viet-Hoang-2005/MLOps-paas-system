const GITHUB_AUTHORIZE_URL = 'https://github.com/login/oauth/authorize';

const createState = () => {
  if (crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

export const getGitHubOAuthConfig = () => ({
  clientId: import.meta.env.VITE_GITHUB_CLIENT_ID || '',
  redirectUri:
    import.meta.env.VITE_GITHUB_REDIRECT_URI ||
    'http://localhost:5173/oauth/github/callback',
});

export const startGitHubOAuth = () => {
  const { clientId, redirectUri } = getGitHubOAuthConfig();

  if (!clientId) {
    throw new Error('VITE_GITHUB_CLIENT_ID is not configured.');
  }

  const state = createState();
  localStorage.setItem('github_oauth_state', state);

  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: 'read:user user:email',
    state,
  });

  window.location.href = `${GITHUB_AUTHORIZE_URL}?${params.toString()}`;
};

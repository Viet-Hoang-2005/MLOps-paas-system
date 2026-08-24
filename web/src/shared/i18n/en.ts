export const commonEn = {
  actions: {
    close: 'Close', cancel: 'Cancel', save: 'Save', retry: 'Retry', confirm: 'Confirm', copy: 'Copy', copied: 'Copied',
    createModel: 'New model', uploadModel: 'Upload your new model', logout: 'Logout', openNavigation: 'Open navigation',
    closeNavigation: 'Close navigation', expandSidebar: 'Expand sidebar', collapseSidebar: 'Collapse sidebar',
  },
  navigation: {
    primary: 'Primary navigation', workspace: 'Workspace', home: 'Home', driftMonitoring: 'Drift Monitoring',
    modelTraining: 'Model Training', modelEvolution: 'Model Evolution', management: 'Management',
    notification: 'Notification', setting: 'Setting',
  },
  modelSelector: {
    label: 'Select model', empty: 'No model selected', search: 'Search model projects', clearSearch: 'Clear model search',
    noMatches: 'No matching model project.',
  },
  theme: { appearance: 'Appearance', current: 'Theme: {{mode}}', light: 'Light', dark: 'Dark', system: 'System' },
  userMenu: { open: 'Open user menu' },
  profile: { fallbackName: 'AI Engineer', initialsFallback: 'User', signedIn: 'Signed in' },
  statuses: {
    registered: 'registered',
    loading: 'Loading...',
    loadingPage: 'Loading page',
    empty: 'No data available',
    error: 'Something went wrong',
    unknown: 'Unknown',
    none: 'None',
    notAvailable: 'Not available',
  },
  pagination: { page: 'Page {{current}} of {{total}}', previous: 'Previous', next: 'Next', empty: 'No records found.' },
  steps: { progress: 'Step {{current}} of {{total}}', progressLabel: 'Progress' },
  csv: { empty: 'No CSV data', range: 'Row {{start}} - {{end}} of {{total}}', column: 'Column {{index}}', previous: 'Previous CSV page', next: 'Next CSV page' },
  errors: { title: 'Something went wrong', description: 'The page could not be displayed safely. Your request was not submitted again.', reload: 'Reload application' },
  terminal: {
    title: 'Console', build: 'Build', stop: 'Stop', rebuild: 'Re-Build',
    copied: 'Logs copied.', copyTitle: 'Copy log', copy: 'Copy', error: 'Error:',
  },
  accessibility: { closeModal: 'Close modal', dismissNotification: 'Dismiss notification', pageSections: 'Page sections', showPassword: 'Show password', hidePassword: 'Hide password' },
} as const;

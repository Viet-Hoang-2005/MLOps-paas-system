import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@/app/styles/globals.css'
import App from '@/app/App'
import { ErrorBoundary } from '@/shared/components/ErrorBoundary'
import { AppProviders } from '@/app/providers/AppProviders'
import { initializeTheme } from '@/app/theme/theme'

initializeTheme()

createRoot(document.getElementById('root')!).render(
  <ErrorBoundary>
    <StrictMode>
      <AppProviders>
        <App />
      </AppProviders>
    </StrictMode>
  </ErrorBoundary>,
)

import { AppRouter } from '@/app/router/AppRouter';
import { ToastContainer } from '@/shared/components/Toast';

export default function App() {
  return (
    <>
      <ToastContainer />
      <AppRouter />
    </>
  );
}

import { Outlet } from 'react-router-dom';
import { Background } from '@/features/auth/components/Background';

export default function AuthLayout() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-background">
      <Background />
      <Outlet />
    </div>
  );
}

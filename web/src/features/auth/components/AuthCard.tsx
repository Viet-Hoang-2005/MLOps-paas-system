import type { ReactNode } from 'react';

interface AuthCardProps {
  children: ReactNode;
  className?: string;
  containerClassName?: string;
  cardClassName?: string;
}

export function AuthCard({
  children,
  className = '',
  containerClassName = '',
  cardClassName = '',
}: AuthCardProps) {
  return (
    <div className={`relative flex min-h-screen items-center justify-center overflow-hidden bg-transparent ${className}`}>
      <div className={`relative z-10 mx-4 w-full max-w-md sm:mx-0 ${containerClassName}`}>
        <div
          className={`
            rounded-overlay border border-[var(--auth-card-border)] bg-[var(--auth-card-background)] p-8
            shadow-2xl backdrop-blur-xl sm:p-10
            ${cardClassName}
          `}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

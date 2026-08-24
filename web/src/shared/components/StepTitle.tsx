import type { ElementType } from 'react';

export interface StepTitleProps {
  title: string;
  subtitle?: string;
  description?: string;
  icon?: ElementType;
}

export function StepTitle({ title, subtitle, description, icon: Icon }: StepTitleProps) {
  const text = subtitle || description;
  return (
    <div className="mb-4">
      <h2 className="flex items-center gap-2 text-style-section-title text-color-foreground">
        {Icon && <Icon className="w-5 h-5 text-color-muted-foreground" />}
        {title}
      </h2>
      {text && <p className="mt-1 text-style-body text-color-muted-foreground">{text}</p>}
    </div>
  );
}

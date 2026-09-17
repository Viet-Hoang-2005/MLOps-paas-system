import { clsx, type ClassValue } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

const mergeClassNames = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [
        {
          'text-style': [
            'display',
            'page-title',
            'section-title',
            'heading',
            'metric',
            'body-lg',
            'body',
            'body-strong',
            'control',
            'caption',
            'caption-strong',
            'overline',
            'code-sm',
            'code-sm-strong',
            'terminal',
          ],
        },
      ],
      'rounded': [
        {
          'rounded': [
            'compact',
            'surface',
            'control',
            'overlay',
            'full',
            'none'
          ],
        },
      ],
      'text-color': [
        {
          'text-color': [
            'foreground',
            'foreground-muted',
            'foreground-subtle',
            'foreground-disabled',
            'foreground-inverse',
            'muted-foreground',
            'primary',
            'primary-hover',
            'primary-active',
            'primary-foreground',
            'brand-accent',
            'accent-foreground',
            'info',
            'info-hover',
            'info-active',
            'info-foreground',
            'success',
            'success-hover',
            'success-active',
            'success-foreground',
            'warning',
            'warning-hover',
            'warning-active',
            'warning-foreground',
            'danger',
            'danger-hover',
            'danger-active',
            'danger-foreground',
            'chart-1',
            'chart-2',
            'chart-3',
            'chart-4',
            'chart-5',
            'chart-6',
            'terminal-foreground',
            'terminal-muted',
            'terminal-info',
            'terminal-success',
            'terminal-warning',
            'terminal-danger',
            'syntax-keyword',
            'syntax-type',
            'syntax-variable',
            'syntax-property',
            'syntax-string',
            'syntax-number',
            'syntax-comment',
            'syntax-function',
          ],
        },
      ],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return mergeClassNames(clsx(inputs));
}

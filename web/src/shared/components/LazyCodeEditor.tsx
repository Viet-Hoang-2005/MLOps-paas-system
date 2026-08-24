import { lazy, Suspense } from 'react';
import type { EditorProps } from '@monaco-editor/react';
import { Skeleton } from './Skeleton';

const MonacoEditor = lazy(() =>
  import('@monaco-editor/react').then((module) => ({ default: module.Editor })),
);

export function LazyCodeEditor(props: EditorProps) {
  return (
    <Suspense fallback={<div className="space-y-3 p-4"><Skeleton className="h-4 w-1/3" /><Skeleton className="h-64 w-full" /></div>}>
      <MonacoEditor {...props} />
    </Suspense>
  );
}

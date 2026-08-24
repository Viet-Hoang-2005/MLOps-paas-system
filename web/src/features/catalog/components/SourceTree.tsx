import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ChevronDown,
  ChevronRight,
  Database,
  FileCode2,
  Folder as FolderIcon,
  Play,
} from 'lucide-react';

import type { CreatingFileState, SourceTreeNode } from './sourceTreeModel';

function InlineTreeInput({ onCommit }: { onCommit: (value: string) => void }) {
  const { t } = useTranslation('catalog');
  const [value, setValue] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const submit = (nextValue: string) => {
    if (submitted) return;
    setSubmitted(true);
    onCommit(nextValue);
  };

  return (
    <input
      autoFocus
      aria-label={t('sourceEditor.fileFolderName')}
      className="min-w-0 flex-1 rounded-compact border border-(--color-primary) bg-(--color-surface) px-1 py-0.5 text-style-body text-(--color-foreground) outline-none focus-visible:ring-2 focus-visible:ring-(--color-ring)"
      value={value}
      onChange={(event) => setValue(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') submit(value);
        if (event.key === 'Escape') submit('');
      }}
      onBlur={() => submit(value)}
    />
  );
}

interface SourceTreeProps {
  nodes: SourceTreeNode[];
  level?: number;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  unsavedContents: Record<string, string>;
  currentEntryPoint?: string;
  expandedFolders: Set<string>;
  toggleFolder: (path: string) => void;
  creatingFile?: CreatingFileState | null;
  onFinishCreating?: (name: string) => void;
  currentParentPath?: string;
}

export function SourceTree({
  nodes,
  level = 0,
  selectedPath,
  onSelect,
  unsavedContents,
  currentEntryPoint,
  expandedFolders,
  toggleFolder,
  creatingFile,
  onFinishCreating,
  currentParentPath = '',
}: SourceTreeProps) {
  return (
    <ul className="space-y-0.5">
      {nodes.map((node) => {
        const isSelected = selectedPath === node.path;
        const isModified = node.type === 'file' && unsavedContents[node.path] !== undefined;
        const isExpanded = expandedFolders.has(node.path);

        if (node.type === 'folder') {
          return (
            <li key={node.path}>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect(node.path);
                  toggleFolder(node.path);
                }}
                className={`flex w-full items-center gap-1.5 rounded-compact px-2 py-1.5 text-left text-style-body transition-colors hover:bg-(--color-muted) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-ring) ${
                  isSelected
                    ? 'bg-(--color-primary-subtle) font-medium text-(--color-primary)'
                    : 'text-(--color-muted-foreground)'
                }`}
                style={{ paddingLeft: `${level * 12 + 8}px` }}
                title={node.path}
              >
                {isExpanded ? (
                  <ChevronDown className="h-4 w-4 shrink-0" />
                ) : (
                  <ChevronRight className="h-4 w-4 shrink-0" />
                )}
                <FolderIcon className="h-4 w-4 shrink-0 text-(--color-primary)" fill="currentColor" />
                <span className="min-w-0 flex-1 truncate">{node.name}</span>
              </button>
              {isExpanded ? (
                <SourceTree
                  nodes={node.children}
                  level={level + 1}
                  selectedPath={selectedPath}
                  onSelect={onSelect}
                  unsavedContents={unsavedContents}
                  currentEntryPoint={currentEntryPoint}
                  expandedFolders={expandedFolders}
                  toggleFolder={toggleFolder}
                  creatingFile={creatingFile}
                  onFinishCreating={onFinishCreating}
                  currentParentPath={node.path}
                />
              ) : null}
            </li>
          );
        }

        return (
          <li key={node.path}>
            <button
              type="button"
              onClick={() => onSelect(node.path)}
              className={`flex w-full items-center gap-1.5 truncate rounded-compact px-2 py-1.5 text-left text-style-body transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-ring) ${
                isSelected
                  ? 'bg-(--color-primary-subtle) font-medium text-(--color-primary)'
                  : 'text-(--color-muted-foreground) hover:bg-(--color-muted)'
              }`}
              style={{ paddingLeft: `${level * 12 + 30}px` }}
              title={node.path}
            >
              {node.name.endsWith('.csv') ? (
                <Database className="h-4 w-4 shrink-0 text-(--color-success)" />
              ) : (
                <FileCode2 className="h-4 w-4 shrink-0 text-(--color-primary)" />
              )}
              <span className="min-w-0 flex-1 truncate">
                {node.name}
                {isModified ? ' *' : ''}
              </span>
              {currentEntryPoint === node.path ? (
                <Play className="h-3 w-3 shrink-0 text-(--color-primary)" />
              ) : null}
            </button>
          </li>
        );
      })}

      {creatingFile &&
      creatingFile.parentPath === currentParentPath &&
      onFinishCreating ? (
        <li key="new-file-input">
          <div
            className="flex items-center gap-1.5 px-2 py-1.5 text-style-body"
            style={{ paddingLeft: `${level * 12 + (creatingFile.type === 'folder' ? 8 : 30)}px` }}
          >
            {creatingFile.type === 'folder' ? (
              <>
                <ChevronRight className="h-4 w-4 shrink-0 text-transparent" />
                <FolderIcon className="h-4 w-4 shrink-0 text-(--color-primary)" fill="currentColor" />
              </>
            ) : (
              <FileCode2 className="h-4 w-4 shrink-0 text-(--color-primary)" />
            )}
            <InlineTreeInput onCommit={onFinishCreating} />
          </div>
        </li>
      ) : null}
    </ul>
  );
}

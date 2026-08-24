import type { WorkspaceFile } from '@/features/catalog/api/catalogApi';

export type CreatingFileState = {
  type: 'file' | 'folder';
  parentPath: string;
};

export type SourceTreeNode = {
  name: string;
  path: string;
  type: 'file' | 'folder';
  children: SourceTreeNode[];
  fileMeta?: WorkspaceFile;
};

export function buildSourceTree(files: WorkspaceFile[]): SourceTreeNode[] {
  const root: SourceTreeNode = { name: 'root', path: '', type: 'folder', children: [] };

  files.forEach((file) => {
    const parts = file.relative_path.split('/');
    let current = root;

    parts.forEach((part, index) => {
      const isFile = index === parts.length - 1;
      if (isFile) {
        if (part !== '.keep') {
          current.children.push({
            name: part,
            path: file.relative_path,
            type: 'file',
            children: [],
            fileMeta: file,
          });
        }
        return;
      }

      let next = current.children.find((child) => child.name === part && child.type === 'folder');
      if (!next) {
        next = {
          name: part,
          path: parts.slice(0, index + 1).join('/'),
          type: 'folder',
          children: [],
        };
        current.children.push(next);
      }
      current = next;
    });
  });

  const sortTree = (node: SourceTreeNode) => {
    node.children.sort((first, second) => {
      if (first.type !== second.type) return first.type === 'folder' ? -1 : 1;
      return first.name.localeCompare(second.name);
    });
    node.children.forEach(sortTree);
  };

  sortTree(root);
  return root.children;
}

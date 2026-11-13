const projectSection =
  /^\/dashboard\/(?:projects\/[^/]+\/)?(overview|deployment|monitoring|training|evolution)\/?$/;

export function projectSelectionPath(
  pathname: string,
  projectId: string,
): string {
  const section = projectSection.exec(pathname)?.[1] ?? "overview";
  return `/dashboard/projects/${projectId}/${section}`;
}

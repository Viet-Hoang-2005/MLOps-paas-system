export function BuildSummaryItem({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-surface border border-border bg-muted p-4">
      <p className="text-style-caption-strong uppercase text-color-muted-foreground">
        {label}
      </p>
      <p className="mt-1 break-all text-style-body-strong text-color-foreground">
        {value}
      </p>
    </div>
  );
}

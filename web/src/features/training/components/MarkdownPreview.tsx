import { Fragment, type ReactNode } from "react";

function inline(text: string): ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g).map((part, index) =>
    part.startsWith("`") ? <code key={index} className="rounded-compact bg-muted px-1 font-mono">{part.slice(1, -1)}</code> :
    part.startsWith("**") ? <strong key={index}>{part.slice(2, -2)}</strong> :
    part.startsWith("*") ? <em key={index}>{part.slice(1, -1)}</em> : <Fragment key={index}>{part}</Fragment>);
}

/** Renders document blocks as React nodes. Embedded HTML stays escaped. */
export function MarkdownPreview({ content }: { content: string }) {
  const lines = content.split(/\r?\n/); const nodes: ReactNode[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const code = [];
      while (++i < lines.length && !lines[i].startsWith("```")) code.push(lines[i]);
      nodes.push(<pre key={i} className="overflow-auto rounded-surface bg-muted p-3 font-mono text-style-body"><code>{code.join("\n")}</code></pre>);
    } else if (/^#{1,6} /.test(line)) {
      const level = line.match(/^#+/)![0].length;
      nodes.push(level === 1 ? <h1 key={i} className="text-style-page-title">{inline(line.slice(level + 1))}</h1> : level === 2 ? <h2 key={i} className="text-style-section-title">{inline(line.slice(level + 1))}</h2> : <h3 key={i} className="text-style-body-strong">{inline(line.slice(level + 1))}</h3>);
    } else if (/^[-*] /.test(line)) {
      const items = [line.slice(2)];
      while (i + 1 < lines.length && /^[-*] /.test(lines[i + 1])) items.push(lines[++i].slice(2));
      nodes.push(<ul key={i} className="list-disc space-y-1 pl-6">{items.map((item, index) => <li key={index}>{inline(item)}</li>)}</ul>);
    } else if (line.trim()) nodes.push(<p key={i} className="whitespace-pre-wrap">{inline(line)}</p>);
  }
  return <article className="space-y-3 p-4 text-style-body">{nodes}</article>;
}

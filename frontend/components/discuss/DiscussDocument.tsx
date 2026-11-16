import { Fragment, type JSX, type ReactNode } from "react";
import type { DiscussSource } from "@/lib/discuss";
import {
  discussTableMinWidth,
  safeExternalUrl,
  splitDiscussCitations,
  splitDiscussDocument,
  type DiscussDocumentBlock,
} from "@/lib/discussLogic";
import { parseMessageMarkdown, type MdBlock, type MdInline } from "@/lib/messageMarkdown";

type SourceTable = Record<string, DiscussSource>;

function sourceLabel(source: DiscussSource): string {
  return `${source.title}（${source.site_name}）`;
}

function renderCitations(text: string, sources: SourceTable, prefix: string): ReactNode[] {
  return splitDiscussCitations(text).map((block, index) => {
    if (block.kind === "text") {
      return <Fragment key={`${prefix}-text-${index}`}>{block.text}</Fragment>;
    }
    const source = sources[block.id];
    const href = source ? safeExternalUrl(source.url) : null;
    if (source && href) {
      return (
        <a
          key={`${prefix}-cite-${index}`}
          className="tag mx-px align-middle whitespace-nowrap"
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          title={sourceLabel(source)}
        >
          {block.id}
        </a>
      );
    }
    return (
      <span
        key={`${prefix}-cite-${index}`}
        className="tag mx-px align-middle whitespace-nowrap"
        title="来源未登记"
      >
        {block.id}
      </span>
    );
  });
}

function renderInline(
  inline: MdInline,
  index: number,
  sources: SourceTable,
  prefix: string,
): ReactNode {
  if (inline.kind === "em") {
    return (
      <em
        key={index}
        className="not-italic [-webkit-text-emphasis:filled_dot_var(--ink2)] [text-emphasis:filled_dot_var(--ink2)] [-webkit-text-emphasis-position:under_right] [text-emphasis-position:under_right]"
      >
        {renderCitations(inline.text, sources, `${prefix}-em-${index}`)}
      </em>
    );
  }
  if (inline.kind === "code") {
    return (
      <code key={index} className="rounded-[4px] bg-[color:var(--chip)] px-[.3em] text-fs-15">
        {inline.text}
      </code>
    );
  }
  return <Fragment key={index}>{renderCitations(inline.text, sources, `${prefix}-text-${index}`)}</Fragment>;
}

function renderInlines(inlines: MdInline[], sources: SourceTable, prefix: string): ReactNode[] {
  return inlines.map((inline, index) => renderInline(inline, index, sources, prefix));
}

function MarkdownBlockView({
  block,
  index,
  sources,
}: {
  block: MdBlock;
  index: number;
  sources: SourceTable;
}): JSX.Element {
  const prefix = `block-${index}`;
  switch (block.kind) {
    case "para":
      return (
        <p className="whitespace-pre-wrap break-words leading-[1.85] text-[color:var(--ink)]">
          {renderInlines(block.inlines, sources, prefix)}
        </p>
      );
    case "heading": {
      const style =
        block.level === 1
          ? "text-fs-18 leading-[1.7] tracking-[.04em] text-[color:var(--ink)]"
          : block.level === 2
            ? "text-fs-16.5 leading-[1.75] tracking-[.04em] text-[color:var(--ink)]"
            : "text-fs-15 tracking-[.08em] text-[color:var(--ink2)]";
      const headingClass = `${style} pt-1`;
      const inlines = renderInlines(block.inlines, sources, prefix);
      if (block.level === 1) {
        return <h3 className={headingClass}>{inlines}</h3>;
      }
      if (block.level === 2) {
        return <h4 className={headingClass}>{inlines}</h4>;
      }
      return <h5 className={headingClass}>{inlines}</h5>;
    }
    case "list": {
      const items = block.items.map((item, itemIndex) => {
        const ordered = block.ordered && item.depth === 0;
        const orderedBefore = block.items
          .slice(0, itemIndex)
          .filter(previous => previous.depth === 0)
          .length;
        const marker = ordered ? `${block.start + orderedBefore}.` : "·";
        return (
          <li
            key={itemIndex}
            className={
              "relative whitespace-pre-wrap break-words pl-[1.4em]"
              + (item.depth === 1 ? " ml-[1.4em]" : "")
              + (itemIndex > 0 ? " mt-[.3em]" : "")
            }
          >
            <span
              aria-hidden="true"
              className={
                "absolute left-0 text-[color:var(--ink2)]"
                + (ordered ? " tabular-nums" : "")
              }
            >
              {marker}
            </span>
            {renderInlines(item.inlines, sources, `${prefix}-item-${itemIndex}`)}
          </li>
        );
      });
      const listClass = "list-none p-0";
      return block.ordered
        ? <ol start={block.start} className={listClass}>{items}</ol>
        : <ul className={listClass}>{items}</ul>;
    }
    case "quote":
      return (
        <blockquote className="whitespace-pre-wrap break-words border-l-2 border-[color:var(--rule)] pl-[1em] text-[color:var(--ink2)]">
          {renderInlines(block.inlines, sources, prefix)}
        </blockquote>
      );
    case "code":
      return (
        <pre className="overflow-x-auto whitespace-pre rounded-[8px] bg-[color:var(--chip)] px-[1em] py-[.75em] font-mono text-fs-13 leading-[1.7] text-[color:var(--ink)]">
          {block.text}
        </pre>
      );
    case "rule":
      return <hr className="my-2 border-0 border-t border-[color:var(--rule)]" />;
  }
}

function TableBlockView({
  block,
  sources,
}: {
  block: Extract<DiscussDocumentBlock, { kind: "table" }>;
  sources: SourceTable;
}): JSX.Element {
  return (
    <div className="max-w-full overflow-x-auto">
      <table
        className="w-full table-fixed border-collapse text-left text-fs-13 leading-[1.7]"
        style={{ minWidth: `${discussTableMinWidth(block.header.length)}em` }}
      >
        <thead>
          <tr>
            {block.header.map((cell, index) => (
              <th
                key={index}
                scope="col"
                className="border-b border-[color:var(--rule)] px-2 py-2 align-top whitespace-pre-wrap break-words font-normal text-[color:var(--ink2)]"
              >
                {renderCitations(cell, sources, `table-head-${index}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td
                  key={cellIndex}
                  className="border-b border-[color:var(--rule)] px-2 py-2 align-top whitespace-pre-wrap break-words text-[color:var(--ink)]"
                >
                  {renderCitations(cell, sources, `table-${rowIndex}-${cellIndex}`)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DiscussDocument({
  text,
  sources,
}: {
  text: string;
  sources: SourceTable;
}): JSX.Element {
  const table = sources ?? {};
  const blocks = splitDiscussDocument(text);
  return (
    <div className="min-w-0 space-y-3 text-[color:var(--ink)]">
      {blocks.map((block, index) => block.kind === "table" ? (
        <TableBlockView key={index} block={block} sources={table} />
      ) : (
        <div key={index} className="min-w-0 space-y-2">
          {parseMessageMarkdown(block.text).map((parsed, parsedIndex) => (
            <MarkdownBlockView key={parsedIndex} block={parsed} index={parsedIndex} sources={table} />
          ))}
        </div>
      ))}
    </div>
  );
}

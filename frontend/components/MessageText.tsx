import { Fragment, type JSX } from "react";
import { parseMessageMarkdown, type MdBlock, type MdInline } from "@/lib/messageMarkdown";

const CARET = (
  <span aria-hidden="true" className="ml-px text-[color:var(--ink)] animate-[blink_1.4s_infinite]">▌</span>
);

const MARK_CLASS = "bg-[color:var(--slip)] text-[color:var(--ink)] rounded-[3px] px-0.5";

function renderHighlighted(text: string, highlight?: string) {
  if (!highlight?.trim()) return text;
  const escaped = highlight.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = text.split(new RegExp(`(${escaped})`, "gi"));
  return parts.map((part, index) =>
    part.toLowerCase() === highlight.toLowerCase()
      ? <mark key={index} className={MARK_CLASS}>{part}</mark>
      : part
  );
}

function renderInline(inline: MdInline, key: number, highlight?: string) {
  if (inline.kind === "em") {
    return (
      <em
        key={key}
        className="not-italic [-webkit-text-emphasis:filled_dot_var(--ink2)] [text-emphasis:filled_dot_var(--ink2)] [-webkit-text-emphasis-position:under_right] [text-emphasis-position:under_right]"
      >
        {renderHighlighted(inline.text, highlight)}
      </em>
    );
  }
  if (inline.kind === "code") {
    return (
      <code key={key} className="rounded-[4px] bg-[color:var(--chip)] px-[.3em] text-fs-15">
        {renderHighlighted(inline.text, highlight)}
      </code>
    );
  }
  return renderHighlighted(inline.text, highlight);
}

function renderInlines(inlines: MdInline[], caret: boolean, highlight?: string) {
  return (
    <>
      {inlines.map((inline, index) => renderInline(inline, index, highlight))}
      {caret ? CARET : null}
    </>
  );
}

function spacing(first: boolean, margin = "mt-[0.75em]"): string {
  return first ? "" : " " + margin;
}

function renderBlock(block: MdBlock, index: number, first: boolean, caret: boolean, highlight?: string): JSX.Element {
  switch (block.kind) {
    case "para":
      return (
        <p key={index} className={"md-block whitespace-pre-wrap" + spacing(first)}>
          {renderInlines(block.inlines, caret, highlight)}
        </p>
      );
    case "heading": {
      const style =
        block.level === 1
          ? "text-fs-18 leading-[1.7] tracking-[.04em] text-[color:var(--ink)]"
          : block.level === 2
            ? "text-fs-18 leading-[1.75] tracking-[.04em] text-[color:var(--ink)]"
            : "tracking-[.08em] text-[color:var(--ink2)]";
      const className = `md-block font-normal ${style}${spacing(first, "mt-[1.1em]")}`;
      const inlines = renderInlines(block.inlines, caret, highlight);
      if (block.level === 1) {
        return (
          <h3 key={index} className={className}>
            {inlines}
          </h3>
        );
      }
      if (block.level === 2) {
        return (
          <h4 key={index} className={className}>
            {inlines}
          </h4>
        );
      }
      return (
        <h5 key={index} className={className}>
          {inlines}
        </h5>
      );
    }
    case "list": {
      let number = block.start;
      const items = block.items.map((item, itemIndex) => {
        const ordered = block.ordered && item.depth === 0;
        const marker = number;
        if (ordered) number += 1;
        const lastItem = itemIndex === block.items.length - 1;
        return (
          <li
            key={itemIndex}
            className={
              "relative whitespace-pre-wrap pl-[1.4em]" +
              (item.depth === 1 ? " ml-[1.4em]" : "") +
              (itemIndex > 0 ? " mt-[.3em]" : "")
            }
          >
            {ordered ? (
              <span aria-hidden="true" className="absolute left-0 tabular-nums text-[color:var(--ink2)]">
                {marker}.
              </span>
            ) : (
              <span
                aria-hidden="true"
                className={
                  "absolute left-[.45em] top-[.85em] h-[4px] w-[4px] rounded-full" +
                  (item.depth === 1 ? " border border-[color:var(--ink3)] bg-transparent" : " bg-[color:var(--ink3)]")
                }
              />
            )}
            {renderInlines(item.inlines, caret && lastItem, highlight)}
          </li>
        );
      });
      const className = "md-block list-none p-0" + spacing(first);
      return block.ordered ? (
        <ol key={index} start={block.start} className={className}>
          {items}
        </ol>
      ) : (
        <ul key={index} className={className}>
          {items}
        </ul>
      );
    }
    case "quote":
      return (
        <blockquote
          key={index}
          className={
            "md-block whitespace-pre-wrap border-l border-[color:var(--rule2)] pl-[1em] text-[color:var(--ink2)]" +
            spacing(first)
          }
        >
          {renderInlines(block.inlines, caret, highlight)}
        </blockquote>
      );
    case "code":
      return (
        <pre
          key={index}
          className={
            "md-block overflow-x-auto whitespace-pre rounded-[8px] bg-[color:var(--chip)] px-[1em] py-[.75em] font-mono text-fs-15 leading-[1.7]" +
            spacing(first)
          }
        >
          {renderHighlighted(block.text, highlight)}
          {caret ? CARET : null}
        </pre>
      );
    case "rule":
      return (
        <Fragment key={index}>
          <hr className="md-block my-[1.2em] border-0 border-t border-[color:var(--rule)]" />
          {caret ? CARET : null}
        </Fragment>
      );
  }
}

export default function MessageText({
  text,
  typing = false,
  caret = false,
  highlight,
}: {
  text: string;
  typing?: boolean;
  caret?: boolean;
  highlight?: string;
}): JSX.Element {
  const blocks = parseMessageMarkdown(text, { typing });
  if (blocks.length === 0) {
    return <>{caret ? CARET : null}</>;
  }
  return <>{blocks.map((block, index) => renderBlock(block, index, index === 0, caret && index === blocks.length - 1, highlight))}</>;
}

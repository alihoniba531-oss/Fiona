export type MdInline =
  | { kind: "text"; text: string }
  | { kind: "em"; text: string }
  | { kind: "code"; text: string };

export type MdListItem = { depth: 0 | 1; inlines: MdInline[] };

export type MdBlock =
  | { kind: "para"; inlines: MdInline[] }
  | { kind: "heading"; level: 1 | 2 | 3; inlines: MdInline[] }
  | { kind: "list"; ordered: boolean; start: number; items: MdListItem[] }
  | { kind: "quote"; inlines: MdInline[] }
  | { kind: "code"; text: string }
  | { kind: "rule" };

const FENCE_RE = /^\s{0,3}```/;
const HEADING_RE = /^\s{0,3}(#{1,6})[ \t]+(.*)$/;
const RULE_RE = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;
const UNORDERED_RE = /^(\s*)([-*+•])\s+(.*)$/;
const ORDERED_RE = /^(\s*)(\d{1,3})(?:[.)]\s+|、\s*)(.*)$/;
const QUOTE_RE = /^\s{0,3}>\s?(.*)$/;

interface DraftListItem {
  depth: 0 | 1;
  text: string;
}

type InlineSegment =
  | { kind: "text"; text: string; start: number }
  | { kind: "code"; text: string; start: number };

function isBlank(line: string): boolean {
  return line.trim() === "";
}

function leadingSpaces(line: string): number {
  const leading = line.match(/^\s*/);
  return leading ? leading[0].length : 0;
}

function isBlockStart(line: string): boolean {
  return (
    FENCE_RE.test(line) ||
    HEADING_RE.test(line) ||
    RULE_RE.test(line) ||
    QUOTE_RE.test(line) ||
    UNORDERED_RE.test(line) ||
    ORDERED_RE.test(line)
  );
}

function headingLevel(hashes: number): 1 | 2 | 3 {
  if (hashes >= 4) return 3;
  if (hashes === 3) return 2;
  return 1;
}

function headingContent(raw: string): string {
  const content = raw.trimEnd();
  let hashStart = content.length;
  while (hashStart > 0 && content[hashStart - 1] === "#") hashStart -= 1;
  if (hashStart === content.length) return content;
  if (hashStart > 0 && content[hashStart - 1].trim() !== "") return content;
  return content.slice(0, hashStart).trimEnd();
}

function scanCode(text: string): { segments: InlineSegment[]; unmatchedBackticks: number[] } {
  const segments: InlineSegment[] = [];
  const unmatchedBackticks: number[] = [];
  let cursor = 0;
  let textStart = 0;
  while (cursor < text.length) {
    if (text[cursor] !== "`") {
      cursor += 1;
      continue;
    }
    const lineEnd = text.indexOf("\n", cursor + 1);
    const limit = lineEnd === -1 ? text.length : lineEnd;
    const closing = text.indexOf("`", cursor + 1);
    if (closing === -1 || closing > limit || closing === cursor + 1) {
      unmatchedBackticks.push(cursor);
      cursor += 1;
      continue;
    }
    if (cursor > textStart) {
      segments.push({ kind: "text", text: text.slice(textStart, cursor), start: textStart });
    }
    segments.push({ kind: "code", text: text.slice(cursor + 1, closing), start: cursor });
    cursor = closing + 1;
    textStart = cursor;
  }
  if (textStart < text.length) {
    segments.push({ kind: "text", text: text.slice(textStart), start: textStart });
  }
  return { segments, unmatchedBackticks };
}

function unmatchedEmphasisPositions(text: string): number[] {
  const unmatched: number[] = [];
  let cursor = 0;
  while (cursor < text.length) {
    const opening = text.indexOf("**", cursor);
    if (opening === -1) break;
    const closing = text.indexOf("**", opening + 2);
    if (closing === -1 || closing === opening + 2) {
      unmatched.push(opening);
      cursor = opening + 2;
      continue;
    }
    cursor = closing + 2;
  }
  return unmatched;
}

function findLastUnmatchedDelimiter(text: string): { index: number; length: number } | null {
  const scan = scanCode(text);
  let bestIndex = -1;
  let bestLength = 0;
  for (const index of scan.unmatchedBackticks) {
    if (index > bestIndex) {
      bestIndex = index;
      bestLength = 1;
    }
  }
  for (const segment of scan.segments) {
    if (segment.kind !== "text") continue;
    for (const relative of unmatchedEmphasisPositions(segment.text)) {
      const index = segment.start + relative;
      if (index > bestIndex) {
        bestIndex = index;
        bestLength = 2;
      }
    }
  }
  return bestIndex === -1 ? null : { index: bestIndex, length: bestLength };
}

function splitEmphasis(text: string): MdInline[] {
  const inlines: MdInline[] = [];
  let cursor = 0;
  let buffer = "";
  while (cursor < text.length) {
    const opening = text.indexOf("**", cursor);
    if (opening === -1) {
      buffer += text.slice(cursor);
      break;
    }
    buffer += text.slice(cursor, opening);
    const closing = text.indexOf("**", opening + 2);
    if (closing === -1 || closing === opening + 2) {
      buffer += "**";
      cursor = opening + 2;
      continue;
    }
    if (buffer) {
      inlines.push({ kind: "text", text: buffer });
      buffer = "";
    }
    inlines.push({ kind: "em", text: text.slice(opening + 2, closing) });
    cursor = closing + 2;
  }
  if (buffer) inlines.push({ kind: "text", text: buffer });
  return inlines;
}

function mergeText(inlines: MdInline[]): MdInline[] {
  const merged: MdInline[] = [];
  for (const inline of inlines) {
    if (inline.kind !== "text") {
      merged.push(inline);
      continue;
    }
    if (!inline.text) continue;
    const previous = merged[merged.length - 1];
    if (previous && previous.kind === "text") {
      merged[merged.length - 1] = { kind: "text", text: previous.text + inline.text };
    } else {
      merged.push({ kind: "text", text: inline.text });
    }
  }
  return merged;
}

function parseInline(raw: string, typing: boolean): MdInline[] {
  let text = raw;
  if (typing) {
    const unmatched = findLastUnmatchedDelimiter(text);
    if (unmatched) {
      text = text.slice(0, unmatched.index) + text.slice(unmatched.index + unmatched.length);
    }
  }
  const inlines: MdInline[] = [];
  for (const segment of scanCode(text).segments) {
    if (segment.kind === "code") {
      inlines.push({ kind: "code", text: segment.text });
    } else {
      inlines.push(...splitEmphasis(segment.text));
    }
  }
  return mergeText(inlines);
}

function parseList(
  lines: string[],
  startIndex: number,
): { block: MdBlock; next: number; lastText: string } {
  const firstUnordered = lines[startIndex].match(UNORDERED_RE);
  const firstOrdered = firstUnordered ? null : lines[startIndex].match(ORDERED_RE);
  const ordered = firstUnordered === null;
  const start = ordered && firstOrdered ? Number(firstOrdered[2]) : 1;
  const items: DraftListItem[] = [];
  let index = startIndex;
  while (index < lines.length) {
    const line = lines[index];
    if (isBlank(line)) break;
    if (RULE_RE.test(line)) break;
    const unordered = line.match(UNORDERED_RE);
    const orderedMatch = unordered ? null : line.match(ORDERED_RE);
    if (unordered || orderedMatch) {
      const match = unordered ?? orderedMatch!;
      const itemOrdered = orderedMatch !== null;
      const depth: 0 | 1 = match[1].length >= 2 && items.length > 0 ? 1 : 0;
      if (depth === 0 && itemOrdered !== ordered) break;
      items.push({ depth, text: match[3] });
      index += 1;
      continue;
    }
    if (leadingSpaces(line) >= 2 && !isBlockStart(line) && items.length > 0) {
      items[items.length - 1].text += "\n" + line.trim();
      index += 1;
      continue;
    }
    break;
  }
  return {
    block: {
      kind: "list",
      ordered,
      start,
      items: items.map((item) => ({
        depth: item.depth,
        inlines: parseInline(item.text, false),
      })),
    },
    next: index,
    lastText: items.length > 0 ? items[items.length - 1].text : "",
  };
}

function parseBlocks(raw: string, typing: boolean): MdBlock[] {
  const lines = raw.replace(/\r\n/g, "\n").split("\n");
  const blocks: MdBlock[] = [];
  let lastInlineSource: string | null = null;
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (isBlank(line)) {
      index += 1;
      continue;
    }

    if (FENCE_RE.test(line)) {
      index += 1;
      const body: string[] = [];
      while (index < lines.length && !FENCE_RE.test(lines[index])) {
        body.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ kind: "code", text: body.join("\n") });
      lastInlineSource = null;
      continue;
    }

    const heading = line.match(HEADING_RE);
    if (heading) {
      const content = headingContent(heading[2]);
      blocks.push({
        kind: "heading",
        level: headingLevel(heading[1].length),
        inlines: parseInline(content, false),
      });
      lastInlineSource = content;
      index += 1;
      continue;
    }

    if (RULE_RE.test(line)) {
      blocks.push({ kind: "rule" });
      lastInlineSource = null;
      index += 1;
      continue;
    }

    if (QUOTE_RE.test(line)) {
      const quoted: string[] = [];
      while (index < lines.length) {
        const quote = lines[index].match(QUOTE_RE);
        if (!quote) break;
        quoted.push(quote[1]);
        index += 1;
      }
      const quotedText = quoted.join("\n");
      blocks.push({ kind: "quote", inlines: parseInline(quotedText, false) });
      lastInlineSource = quotedText;
      continue;
    }

    if (UNORDERED_RE.test(line) || ORDERED_RE.test(line)) {
      const parsed = parseList(lines, index);
      blocks.push(parsed.block);
      lastInlineSource = parsed.lastText;
      index = parsed.next;
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length) {
      const current = lines[index];
      if (isBlank(current)) break;
      if (paragraph.length > 0 && isBlockStart(current)) break;
      paragraph.push(current);
      index += 1;
    }
    const paragraphText = paragraph.join("\n");
    blocks.push({ kind: "para", inlines: parseInline(paragraphText, false) });
    lastInlineSource = paragraphText;
  }
  if (typing && lastInlineSource !== null && blocks.length > 0) {
    const last = blocks[blocks.length - 1];
    const recomputed = parseInline(lastInlineSource, true);
    if (last.kind === "para" || last.kind === "heading" || last.kind === "quote") {
      last.inlines = recomputed;
    } else if (last.kind === "list" && last.items.length > 0) {
      last.items[last.items.length - 1].inlines = recomputed;
    }
  }
  return blocks;
}

export function parseMessageMarkdown(
  text: string,
  options?: { typing?: boolean },
): MdBlock[] {
  try {
    return parseBlocks(typeof text === "string" ? text : "", options?.typing === true);
  } catch {
    return typeof text === "string" && text
      ? [{ kind: "para", inlines: [{ kind: "text", text }] }]
      : [];
  }
}

function inlinesToPlainText(inlines: MdInline[]): string {
  let text = "";
  for (const inline of inlines) {
    text += inline.text;
  }
  return text;
}

export function stripMessageMarkdown(text: string): string {
  const blocks = parseMessageMarkdown(text);
  const parts: string[] = [];
  for (const block of blocks) {
    switch (block.kind) {
      case "para":
      case "heading":
      case "quote":
        parts.push(inlinesToPlainText(block.inlines));
        break;
      case "code":
        parts.push(block.text);
        break;
      case "list": {
        let number = block.start;
        const items = block.items.map((item) => {
          if (block.ordered && item.depth === 0) {
            const line = `${number}. ${inlinesToPlainText(item.inlines)}`;
            number += 1;
            return line;
          }
          return `· ${inlinesToPlainText(item.inlines)}`;
        });
        parts.push(items.join("\n"));
        break;
      }
      case "rule":
        break;
    }
  }
  return parts.join("\n\n");
}

const SENTENCE_ENDINGS = new Set(["。", "！", "？", "!", "?", "；", ";", "\n"]);
const PERIODS = new Set([".", "．"]);

function isDigit(ch: string | undefined): boolean {
  return !!ch && /[0-9０-９]/.test(ch);
}

function isSentenceEnd(text: string, index: number): boolean {
  const ch = text[index];
  if (SENTENCE_ENDINGS.has(ch)) return true;
  if (!PERIODS.has(ch)) return false;
  // A period between digits is a date/time/decimal separator, not a sentence end.
  return !(isDigit(text[index - 1]) && isDigit(text[index + 1]));
}

/**
 * Split text into TTS-sized chunks without losing content.
 * Sentences end at Chinese/English sentence punctuation and newlines; a period
 * between two digits is kept inside the sentence. Adjacent sentences are packed
 * greedily up to `max`, and an oversized sentence is hard-cut at `max`.
 */
export function splitTtsChunks(text: string, max = 250): string[] {
  if (!text || !text.trim()) return [];
  const normalizedMax = Number.isFinite(max) ? Math.floor(max) : 250;
  const limit = normalizedMax >= 1 ? normalizedMax : 250;

  const sentences: string[] = [];
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    if (!isSentenceEnd(text, i)) continue;
    let end = i + 1;
    // Keep runs like "？！" or "..." together instead of emitting punctuation-only chunks.
    while (end < text.length && text[end] !== "\n" && isSentenceEnd(text, end)) end += 1;
    sentences.push(text.slice(start, end));
    start = end;
    i = end - 1;
  }
  if (start < text.length) sentences.push(text.slice(start));

  const units: string[] = [];
  for (const sentence of sentences) {
    const trimmed = sentence.trim();
    if (!trimmed) continue;
    if (trimmed.length <= limit) {
      units.push(trimmed);
      continue;
    }
    for (let offset = 0; offset < trimmed.length; offset += limit) {
      const piece = trimmed.slice(offset, offset + limit).trim();
      if (piece) units.push(piece);
    }
  }

  const chunks: string[] = [];
  let buffer = "";
  for (const unit of units) {
    if (!buffer) {
      buffer = unit;
    } else if (buffer.length + unit.length <= limit) {
      buffer += unit;
    } else {
      chunks.push(buffer);
      buffer = unit;
    }
  }
  if (buffer) chunks.push(buffer);
  return chunks;
}

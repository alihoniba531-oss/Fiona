export function avatarGlyph(avatar?: string): string | null {
  const value = avatar?.trim();
  if (!value || value === "✨") return null;

  if (typeof Intl.Segmenter === "function") {
    const segments = new Intl.Segmenter("zh", { granularity: "grapheme" }).segment(value);
    return segments[Symbol.iterator]().next().value?.segment ?? null;
  }

  return Array.from(value)[0] ?? null;
}

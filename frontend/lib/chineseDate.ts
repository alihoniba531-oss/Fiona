import { beijingParts } from "@/lib/beijingTime";

const digits = "零一二三四五六七八九";

function chineseNumber(value: number): string {
  if (value < 10) return digits[value];
  return `${value >= 20 ? digits[Math.floor(value / 10)] : ""}十${value % 10 ? digits[value % 10] : ""}`;
}

export function formatChineseDate(date: Date, includeYear = false): string {
  const parts = beijingParts(date);
  const year = includeYear ? `${parts.year}年` : "";
  return `${year}${chineseNumber(parts.month)}月${chineseNumber(parts.day)}日`;
}

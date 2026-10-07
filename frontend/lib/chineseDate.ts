const digits = "零一二三四五六七八九";

function chineseNumber(value: number): string {
  if (value < 10) return digits[value];
  return `${value >= 20 ? digits[Math.floor(value / 10)] : ""}十${value % 10 ? digits[value % 10] : ""}`;
}

export function formatChineseDate(date: Date, includeYear = false): string {
  const year = includeYear ? `${date.getFullYear()}年` : "";
  return `${year}${chineseNumber(date.getMonth() + 1)}月${chineseNumber(date.getDate())}日`;
}

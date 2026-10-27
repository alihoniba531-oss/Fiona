export const BEIJING_OFFSET_MS = 8 * 3600_000;

const DAY_MS = 86_400_000;
const INVALID_PARTS = {
  year: NaN, month: NaN, day: NaN, hour: NaN, minute: NaN, second: NaN, weekday: NaN,
};

function isInvalid(date: Date): boolean {
  return Number.isNaN(date.getTime());
}

export function beijingParts(date: Date): { year: number; month: number; day: number; hour: number; minute: number; second: number; weekday: number } {
  if (isInvalid(date)) return { ...INVALID_PARTS };
  const shifted = new Date(date.getTime() + BEIJING_OFFSET_MS);
  return {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth() + 1,
    day: shifted.getUTCDate(),
    hour: shifted.getUTCHours(),
    minute: shifted.getUTCMinutes(),
    second: shifted.getUTCSeconds(),
    weekday: shifted.getUTCDay(),
  };
}

export function beijingDayNumber(date: Date): number {
  return Math.floor((date.getTime() + BEIJING_OFFSET_MS) / DAY_MS);
}

export function beijingDateKey(date: Date): string {
  if (isInvalid(date)) return "";
  const parts = beijingParts(date);
  return `${String(parts.year).padStart(4, "0")}-${String(parts.month).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}`;
}

export function beijingDayStart(dateKey: string): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateKey);
  if (!match) return new Date(NaN);
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const utc = Date.UTC(year, month - 1, day);
  const check = new Date(utc);
  if (check.getUTCFullYear() !== year || check.getUTCMonth() !== month - 1 || check.getUTCDate() !== day) {
    return new Date(NaN);
  }
  return new Date(utc - BEIJING_OFFSET_MS);
}

export function formatBeijingTime(date: Date): string {
  if (isInvalid(date)) return "";
  const shifted = new Date(date.getTime() + BEIJING_OFFSET_MS);
  return `${String(shifted.getUTCHours()).padStart(2, "0")}:${String(shifted.getUTCMinutes()).padStart(2, "0")}`;
}

export function formatBeijingDateTime(date: Date, withSeconds = false): string {
  if (isInvalid(date)) return "";
  const shifted = new Date(date.getTime() + BEIJING_OFFSET_MS);
  const day = `${shifted.getUTCFullYear()}/${String(shifted.getUTCMonth() + 1).padStart(2, "0")}/${String(shifted.getUTCDate()).padStart(2, "0")}`;
  const time = `${String(shifted.getUTCHours()).padStart(2, "0")}:${String(shifted.getUTCMinutes()).padStart(2, "0")}`;
  return withSeconds ? `${day} ${time}:${String(shifted.getUTCSeconds()).padStart(2, "0")}` : `${day} ${time}`;
}

export function formatBeijingDateLong(date: Date): string {
  if (isInvalid(date)) return "";
  const parts = beijingParts(date);
  return `${parts.year}年${parts.month}月${parts.day}日`;
}

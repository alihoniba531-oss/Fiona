import { clsx, type ClassValue } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"

// 字阶令牌 text-fs-*（见 app/globals.css）登记为字号组，否则 tailwind-merge 会把它们当成文字颜色，与颜色类互相吞掉。
const twMerge = extendTailwindMerge({
  extend: { theme: { text: ["fs-11", "fs-12", "fs-13", "fs-15", "fs-16.5", "fs-18", "fs-22", "fs-30", "fs-46", "fs-76"] } },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

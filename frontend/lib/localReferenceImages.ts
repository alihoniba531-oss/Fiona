import { isLocalReferenceDataUrl } from "@/lib/generatedImages";

export const MAX_REFERENCE_FILE_BYTES = 5 * 1024 * 1024;
export const REFERENCE_FILE_TYPES = ["image/png", "image/jpeg", "image/webp"];

export async function readLocalReferenceImage(file: File, signal: AbortSignal): Promise<string> {
  if (!REFERENCE_FILE_TYPES.includes(file.type)) throw new Error("参考图仅支持 PNG、JPEG、WebP 格式。");
  if (!file.size || file.size > MAX_REFERENCE_FILE_BYTES) throw new Error("每张参考图需大于 0 字节且不超过 5MB。");
  const header = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  signal.throwIfAborted();
  const matchesFormat = file.type === "image/png"
    ? [137, 80, 78, 71, 13, 10, 26, 10].every((byte, index) => header[index] === byte)
    : file.type === "image/jpeg" ? header[0] === 255 && header[1] === 216 && header[2] === 255
    : String.fromCharCode(...header.slice(0, 4)) === "RIFF" && String.fromCharCode(...header.slice(8, 12)) === "WEBP";
  if (!matchesFormat) throw new Error("图片内容与文件格式不符，请选择有效的 PNG、JPEG 或 WebP 图片。");
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    const abort = () => { reader.abort(); reject(new DOMException("读取已取消", "AbortError")); };
    if (signal.aborted) { abort(); return; }
    signal.addEventListener("abort", abort, { once: true });
    reader.onload = () => {
      if (typeof reader.result === "string" && isLocalReferenceDataUrl(reader.result)) resolve(reader.result);
      else reject(new Error("无法读取参考图，请重新选择。"));
    };
    reader.onerror = () => reject(new Error("无法读取参考图，请重新选择。"));
    reader.onloadend = () => signal.removeEventListener("abort", abort);
    reader.readAsDataURL(file);
  });
  // Reject corrupt files before they enter the composer. This decodes a local
  // data URL only; no network request or authenticated fetch is involved.
  await new Promise<void>((resolve, reject) => {
    const preview = new Image();
    const cleanup = () => { signal.removeEventListener("abort", abort); preview.onload = null; preview.onerror = null; };
    const abort = () => { cleanup(); preview.src = ""; reject(new DOMException("读取已取消", "AbortError")); };
    if (signal.aborted) { abort(); return; }
    signal.addEventListener("abort", abort, { once: true });
    preview.onload = () => {
      cleanup();
      if (preview.naturalWidth && preview.naturalHeight) resolve();
      else reject(new Error("参考图内容无效，请选择有效图片。"));
    };
    preview.onerror = () => { cleanup(); reject(new Error("参考图已损坏或格式不受支持，请重新选择。")); };
    preview.src = dataUrl;
  });
  return dataUrl;
}

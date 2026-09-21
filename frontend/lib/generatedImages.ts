import { API_BASE } from "@/lib/config";

// Only files created by the image provider can be selected as edit references.
// Strip our API prefix for requests; never send the preview's blob URL.
export function generatedImagePath(imageUrl: string | undefined): string | null {
  if (!imageUrl) return null;
  const path = imageUrl.startsWith(`${API_BASE}/`)
    ? imageUrl.slice(API_BASE.length) : imageUrl;
  return /^\/uploads\/generated_[a-f0-9]{32}\.png$/.test(path) ? path : null;
}

export function referenceImagePath(imageUrl: string | undefined): string | null {
  if (!imageUrl) return null;
  const path = imageUrl.startsWith(`${API_BASE}/`)
    ? imageUrl.slice(API_BASE.length) : imageUrl;
  return /^\/uploads\/(?:generated|reference)_[a-f0-9]{32}\.png$/.test(path) ? path : null;
}

export type ReferenceImageInput =
  | { image_path: string; image_base64?: never }
  | { image_base64: string; image_path?: never };

export function isLocalReferenceDataUrl(value: string): boolean {
  return /^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(value);
}

export function referencePreviewUrl(reference: ReferenceImageInput): string {
  return reference.image_path ? `${API_BASE}${reference.image_path}` : reference.image_base64!;
}

// New history records keep ordered references; old records keep only image_path.
// Return one list so the legacy first image is never rendered twice.
export function storedReferenceImagePaths(paths: unknown, legacyImagePath?: string | null): string[] {
  const references = Array.isArray(paths)
    ? paths.map(path => typeof path === "string" ? referenceImagePath(path) : null).filter((path): path is string => !!path)
    : [];
  if (references.length) return [...new Set(references)].slice(0, 3);
  const legacy = referenceImagePath(legacyImagePath ?? undefined);
  return legacy ? [legacy] : [];
}

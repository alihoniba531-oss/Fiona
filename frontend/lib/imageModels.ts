import type { ImageModelId } from "@/components/ChatBubble";

export const DEFAULT_IMAGE_MODEL = "qwen-image-3.0";

export interface ImageModelOption {
  id: ImageModelId;
  label: string;
  shortLabel: string;
  available: boolean;
}

export const FALLBACK_IMAGE_MODELS: ImageModelOption[] = [
  { id: DEFAULT_IMAGE_MODEL, label: "Qwen Image 3.0", shortLabel: "Qwen 3.0", available: true },
  { id: "seedream-5.0-flash", label: "Seedream 5.0 Flash", shortLabel: "Seedream 5.0 Flash", available: true },
];

const modelLabels = new Map<string, string>([
  ...FALLBACK_IMAGE_MODELS.map(model => [model.id, model.label] as [string, string]),
  ["qwen-image-3.0-pro", "Qwen Image 3.0 Pro"],
  ["doubao-seedream-5-0-flash-260915", "Seedream 5.0 Flash"],
]);

/** Unknown model ids keep only the image's AI disclosure, rather than inventing a name. */
export function imageModelLabel(model?: string): string | null {
  return model ? modelLabels.get(model) ?? null : null;
}

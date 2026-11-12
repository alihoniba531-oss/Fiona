import { apiJson } from "@/lib/agents";
import { API_BASE } from "@/lib/config";

export interface NovelFeedbackNote {
  sent_at: string;
  status: "pending" | "delivered" | null;
  delivered_chapter: number | null;
  adopted: boolean | null;
  response: string | null;
  planned_chapter: number | null;
  planned_adopted: boolean | null;
  planned_response: string | null;
}

export interface NovelFeedbackBook {
  status: string;
  chapters_done: number;
  max_chapters: number | null;
  awaiting_chapter: number | null;
  awaiting_is_final: boolean;
  pending_notes: number;
  automation: string;
  redo_cost: "strawberries" | "own_model" | "free";
  plan_row_status: string | null;
  redo_pending: boolean;
}

export interface NovelFeedbackView {
  id: string;
  novel_id: string | null;
  book_title: string;
  next_chapters: string;
  current_plan: string;
  plan_chapter: number | null;
  written: { chapter: number; title: string; issue: string }[];
  note: NovelFeedbackNote | null;
  redo_started_at: string | null;
  book: NovelFeedbackBook | null;
  created_at: string;
}

const feedbackPath = (id: string) => API_BASE + "/novels/feedback/" + encodeURIComponent(id);

export const getNovelFeedback = (id: string, signal?: AbortSignal) => apiJson<NovelFeedbackView>(feedbackPath(id), { signal });
export const sendNovelFeedbackNote = (id: string, signal?: AbortSignal) => apiJson<NovelFeedbackView>(feedbackPath(id) + "/note", { method: "POST", signal });
export const redoNovelFeedbackPlan = (id: string, signal?: AbortSignal) => apiJson<NovelFeedbackView>(feedbackPath(id) + "/redo", { method: "POST", signal });

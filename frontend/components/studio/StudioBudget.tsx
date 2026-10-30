import type { StudioAccess } from "@/lib/studio";

export default function StudioBudget({ access }: { access: StudioAccess }) {
  return <div className="ceramic-card mt-4 flex min-w-0 flex-wrap items-center gap-x-6 gap-y-2 rounded-xl p-4 text-fs-13" aria-label="今日额度">
    <p>今日额度 <span className="readout">¥{access.today.committed_cny.toFixed(2)} / ¥{access.caps.daily_cny.toFixed(2)}</span></p>
    <p>剩余 <span className="readout">¥{access.today.remaining_cny.toFixed(2)}</span></p>
    <p className="w-full">Claude 本月 <span className="readout">${(access.caps.brain_month_used_usd ?? 0).toFixed(2)} / ${(access.caps.brain_monthly_usd ?? 40).toFixed(2)}</span></p>
  </div>;
}

"use client";

import { novelModelOptions, type NovelCatalog, type NovelPanelMode } from "@/lib/novels";

export const novelFieldClass = "ceramic-card w-full min-w-0 rounded-[10px] border-0 px-3 py-3 text-fs-16.5 leading-[1.8] tracking-normal text-[color:var(--ink)] outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ink)] disabled:opacity-50";

export default function NovelModelFields({ catalog, agents, onChange, disabled = false, allowRoleChanges = false, panelMode = "critique" }: {
  catalog: NovelCatalog; agents: Record<string, string>; onChange: (agents: Record<string, string>) => void;
  disabled?: boolean; allowRoleChanges?: boolean; panelMode?: NovelPanelMode;
}) {
  const advisors = catalog.agents.filter(agent => !["editor", "writer", "archivist", "reviewer"].includes(agent.id));
  const selectedAdvisors = advisors.filter(agent => agents[agent.id]).length;
  const toggle = (role: string, enabled: boolean) => {
    const next = { ...agents };
    if (enabled) next[role] = novelModelOptions(catalog, role)[0]?.value ?? "";
    else delete next[role];
    onChange(next);
  };
  const renderRole = (agent: NovelCatalog["agents"][number], advisor = false) => {
    const selected = !!agents[agent.id];
    const roleDisabled = disabled || advisor && panelMode === "solo";
    const options = novelModelOptions(catalog, agent.id);
    const selectedModel = agents[agent.id] ?? options[0]?.value ?? "";
    const price = catalog.models.find(model => model.id === selectedModel)?.price;
    return <div key={agent.id} className="min-w-0 border-b border-[color:var(--carve)] py-4 last:border-b-0">
      <div className="flex flex-wrap items-center gap-2">
        {agent.required || !allowRoleChanges ? <span className="text-fs-16.5">{agent.name}</span> : <label className="flex min-h-10 items-center gap-2 text-fs-16.5"><input type="checkbox" className="h-5 w-5 accent-[color:var(--ink)]" checked={selected} disabled={roleDisabled || advisor && !selected && selectedAdvisors >= 5} onChange={event => toggle(agent.id, event.target.checked)} />{agent.name}</label>}
        {agent.required && <span className="tag">必选</span>}
      </div>
      <p className="mb-2 text-fs-13 leading-[1.85] text-[color:var(--ink2)]">{agent.description}</p>
      <label className="block"><span className="sr-only">{agent.name}的模型</span><select className={novelFieldClass} value={selectedModel} disabled={roleDisabled || !selected} onChange={event => onChange({ ...agents, [agent.id]: event.target.value })}>{options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      <p className="mt-2 hidden min-w-0 whitespace-normal break-words text-fs-13 leading-[1.85] text-[color:var(--ink2)] mobile:block">{selectedModel === "byok:self" ? options.find(option => option.value === selectedModel)?.label ?? "我的模型暂不可用，请重新选择。" : price ? <>每千 token 输入/输出约 <span className="readout">{price.input}/{price.output}</span> 草莓</> : "请选择可用模型。"}</p>
      {agent.id === "editor" && <p className="mt-2 text-fs-13 leading-[1.85] text-[color:var(--ink2)]">{catalog.notice}</p>}
    </div>;
  };
  return <div className="min-w-0">
    {catalog.agents.filter(agent => agent.required || agent.id === "reviewer").filter(agent => allowRoleChanges || agents[agent.id]).map(agent => renderRole(agent))}
    <fieldset disabled={disabled || panelMode === "solo"} className={`mt-5 min-w-0 ${panelMode === "solo" ? "opacity-50" : ""}`}>
      <legend className="text-fs-16.5 tracking-[.12em]">顾问 <span className="readout text-fs-13">{selectedAdvisors} / 5</span></legend>
      {panelMode === "solo" && <p className="mt-2 text-fs-13 leading-[1.85] text-[color:var(--ink2)]">主编独自构思时，顾问不参与推演，也不计入估算与提交。</p>}
      {advisors.filter(agent => allowRoleChanges || agents[agent.id]).map(agent => renderRole(agent, true))}
    </fieldset>
  </div>;
}

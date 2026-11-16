"use client";

import { useRef } from "react";
import { Plus } from "lucide-react";

export interface DiscussTeamMember {
  key: string;
  role?: string;
  name: string;
  does: string;
  focus?: string;
}

export interface DiscussTeamEditorProps {
  members: DiscussTeamMember[];
  rolePool: { id: string; name: string; does: string }[];
  maxMembers: number;
  nameMax: number;
  doesMax: number;
  focusMax?: number;
  mode: "create" | "plan";
  disabled?: boolean;
  onChange: (members: DiscussTeamMember[]) => void;
}

const fieldClass = "ceramic-card min-h-10 w-full min-w-0 rounded-[10px] px-3 py-2 text-fs-15 text-[color:var(--ink)] outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ink)] disabled:opacity-50";

// 新建页与方案编辑共用的队伍编辑器。只负责把完整的成员数组交回父组件，
// 不校验、不发请求，成员数量与字段长度由父组件与后端把关。
export default function DiscussTeamEditor({
  members,
  rolePool,
  maxMembers,
  nameMax,
  doesMax,
  focusMax,
  mode,
  disabled = false,
  onChange,
}: DiscussTeamEditorProps) {
  const customSeq = useRef(0);
  const atLimit = members.length >= maxMembers;
  const roleName = (member: DiscussTeamMember) =>
    rolePool.find(role => role.id === member.role)?.name ?? "自定义成员";
  const update = (key: string, patch: Partial<DiscussTeamMember>) => {
    onChange(members.map(member => member.key === key ? { ...member, ...patch } : member));
  };
  const toggleRole = (role: { id: string; name: string; does: string }, checked: boolean) => {
    if (checked) {
      if (atLimit) return;
      onChange([...members, {
        key: role.id,
        role: role.id,
        name: role.name,
        does: role.does,
        ...(mode === "plan" ? { focus: "" } : {}),
      }]);
      return;
    }
    onChange(members.filter(member => member.role !== role.id));
  };
  const addCustom = () => {
    if (atLimit) return;
    const used = new Set(members.map(member => member.key));
    let key = `custom-new-${customSeq.current}`;
    while (used.has(key)) {
      customSeq.current += 1;
      key = `custom-new-${customSeq.current}`;
    }
    customSeq.current += 1;
    onChange([...members, {
      key,
      name: "",
      does: "",
      ...(mode === "plan" ? { focus: "" } : {}),
    }]);
  };
  const remove = (key: string) => {
    onChange(members.filter(member => member.key !== key));
  };

  return <div className="min-w-0 space-y-4">
    <p className="text-fs-13 text-[color:var(--ink2)]">已选人数 <span className="readout text-[color:var(--ink)]">{members.length} / {maxMembers}</span></p>
    <fieldset className="min-w-0">
      <legend className="mb-2 text-fs-13">角色池</legend>
      <div className="grid grid-cols-1 gap-2">
        {rolePool.map(role => {
          const checked = members.some(member => member.role === role.id);
          return <label key={role.id} className="flex min-h-10 min-w-0 items-start gap-2 text-fs-13">
            <input
              type="checkbox"
              checked={checked}
              disabled={disabled || (!checked && atLimit)}
              onChange={event => toggleRole(role, event.target.checked)}
              className="mt-1 h-4 w-4 shrink-0 accent-[color:var(--ink)]"
            />
            <span className="min-w-0 break-words"><span>{role.name}</span><span className="ml-2 text-[color:var(--ink2)]">{role.does}</span></span>
          </label>;
        })}
      </div>
    </fieldset>
    {members.length > 0 && <div className="space-y-3">
      {members.map(member => <div key={member.key} className="min-w-0 border border-[color:var(--carve)] p-3">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p className="min-w-0 break-words text-fs-13">{roleName(member)}</p>
          <button type="button" disabled={disabled} onClick={() => remove(member.key)} className="btn btn-quiet min-h-10">删除</button>
        </div>
        <div className="grid grid-cols-2 gap-3 mobile:grid-cols-1">
          <label className="block min-w-0 space-y-1">
            <span className="text-fs-12 text-[color:var(--ink2)]">名字</span>
            <input
              type="text"
              value={member.name}
              maxLength={nameMax}
              disabled={disabled}
              onChange={event => update(member.key, { name: event.target.value })}
              className={fieldClass}
            />
          </label>
          <label className="block min-w-0 space-y-1">
            <span className="text-fs-12 text-[color:var(--ink2)]">职责</span>
            <input
              type="text"
              value={member.does}
              maxLength={doesMax}
              disabled={disabled}
              onChange={event => update(member.key, { does: event.target.value })}
              className={fieldClass}
            />
          </label>
          {mode === "plan" && <label className="block min-w-0 space-y-1">
            <span className="text-fs-12 text-[color:var(--ink2)]">分工</span>
            <input
              type="text"
              value={member.focus ?? ""}
              maxLength={focusMax}
              disabled={disabled}
              onChange={event => update(member.key, { focus: event.target.value })}
              className={fieldClass}
            />
          </label>}
        </div>
      </div>)}
    </div>}
    <button type="button" disabled={disabled || atLimit} onClick={addCustom} className="btn min-h-10"><Plus size={14} />添加自定义成员</button>
  </div>;
}

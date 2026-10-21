"use client";
import { useEffect, useState } from "react";
import { fmt, parseTime } from "@/lib/api";

export default function TimeField({ label, value, max, onChange }: { label: string; value: number; max: number; onChange: (v: number) => void }) {
  const [text, setText] = useState(fmt(value));
  useEffect(() => setText(fmt(value)), [value]);
  const clamp = (v: number) => Math.min(Math.max(0, v), max);
  const commit = () => { const v = parseTime(text); if (v === null) setText(fmt(value)); else onChange(clamp(v)); };
  return (
    <label className="grid gap-1 text-xs text-dim">
      {label}
      <input className="field tnum w-28" inputMode="decimal" value={text} aria-describedby="time-help"
             onChange={(e) => setText(e.target.value)} onBlur={commit}
             onKeyDown={(e) => {
               if (e.key === "Enter") commit();
               if (e.key === "ArrowUp" || e.key === "ArrowDown") { e.preventDefault(); onChange(clamp(value + (e.key === "ArrowUp" ? 1 : -1) * (e.shiftKey ? 5 : 0.5))); }
             }} />
    </label>
  );
}

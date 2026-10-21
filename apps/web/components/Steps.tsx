"use client";
import { motion } from "motion/react";

const STEPS = ["Queued", "Analyzing", "Comparing"];

/** Reflects the real job state (queued → processing → searching). No invented percentages. */
export default function Steps({ active }: { active: number }) {
  return (
    <div role="status" aria-live="polite" className="grid gap-3">
      <ol className="flex items-center gap-2">
        {STEPS.map((s, i) => (
          <li key={s} className="flex items-center gap-2 text-sm" aria-current={i === active ? "step" : undefined}>
            <motion.span animate={{ scale: i === active ? [1, 1.25, 1] : 1 }} transition={{ repeat: i === active ? Infinity : 0, duration: 1.4 }}
                         className="grid h-6 w-6 place-items-center rounded-full text-xs font-semibold"
                         style={{ background: i <= active ? "#8BE0C1" : "rgba(255,255,255,.08)", color: i <= active ? "#06130e" : "#A6ADB8" }}>
              {i < active ? "✓" : i + 1}
            </motion.span>
            <span style={{ color: i <= active ? "#F3F4F6" : "#A6ADB8" }}>{s}</span>
            {i < STEPS.length - 1 && <span aria-hidden="true" className="mx-1 h-px w-6 bg-white/15" />}
          </li>))}
      </ol>
      <div className="shimmer h-1 rounded-full" aria-hidden="true" />
    </div>
  );
}

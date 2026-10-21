"use client";
import { motion } from "motion/react";

export default function Segmented<T extends string>({ id, value, options, onChange, label }:
  { id: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="relative inline-flex rounded-full bg-white/5 p-1">
      {options.map((o) => {
        const on = value === o.value;
        return (
          <button key={o.value} aria-pressed={on} onClick={() => onChange(o.value)}
                  className="relative z-10 rounded-full px-4 py-1.5 text-sm font-medium transition-colors duration-150" style={{ color: on ? "#06130e" : "#A6ADB8" }}>
            {on && <motion.span layoutId={`seg-${id}`} className="absolute inset-0 -z-10 rounded-full bg-accent" transition={{ type: "spring", stiffness: 500, damping: 36 }} />}
            {o.label}
          </button>);
      })}
    </div>
  );
}

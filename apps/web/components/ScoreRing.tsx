"use client";
import { motion } from "motion/react";
import { useId } from "react";

/** Animated ring for an experimental similarity score in [0,1]. Not a percentage of musical similarity. */
export default function ScoreRing({ value, size = 64, stroke = 6, label = "Similarity score" }: { value: number; size?: number; stroke?: number; label?: string }) {
  const gid = useId().replace(/:/g, "");
  const v = Math.max(0, Math.min(1, value));
  const r = (size - stroke) / 2, c = 2 * Math.PI * r;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={`${label}: ${v.toFixed(2)} (experimental)`}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <defs><linearGradient id={gid} x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="#8BE0C1" /><stop offset="100%" stopColor="#6fd0ff" /></linearGradient></defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,.08)" strokeWidth={stroke} />
        <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={`url(#${gid})`} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - v) }} transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }} />
      </svg>
      <span className="tnum absolute inset-0 grid place-items-center font-semibold" style={{ fontSize: size * 0.28 }}>{v.toFixed(2)}</span>
    </div>
  );
}

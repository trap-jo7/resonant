import type { Track } from "@/lib/api";

export default function Artwork({ track, size = 56, glow = false }: { track: Track; size?: number; glow?: boolean }) {
  const hue = [...track.title].reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
  const style = { width: size, height: size, boxShadow: glow ? `0 18px 50px -14px hsl(${hue} 70% 55% / .65)` : undefined };
  if (track.artwork_url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={track.artwork_url} alt={`Artwork for ${track.title}`} style={style} className="shrink-0 rounded-xl object-cover" />;
  }
  return (
    <div aria-hidden="true" style={{ ...style, background: `linear-gradient(135deg, hsl(${hue} 55% 42%), hsl(${(hue + 55) % 360} 55% 22%))` }}
         className="flex shrink-0 items-center justify-center rounded-xl font-semibold text-white/90" >
      <span style={{ fontSize: size * 0.4 }}>{track.title.slice(0, 1).toUpperCase()}</span>
    </div>
  );
}

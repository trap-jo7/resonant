export default function Equalizer({ active, className = "" }: { active: boolean; className?: string }) {
  return (<span aria-hidden="true" className={`eq ${active ? "on" : ""} ${className}`}><i /><i /><i /><i /></span>);
}

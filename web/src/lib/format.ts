export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diff / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return months < 12 ? `${months}mo ago` : `${Math.floor(months / 12)}y ago`;
}

export function pct(value: number | null | undefined): string {
  return value == null ? "–" : `${Math.round(value * 100)}%`;
}

export function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function describeLocation(loc: { scope: string; countries: string[]; regions: string[]; text: string | null }): string {
  switch (loc.scope) {
    case "worldwide":
      return "Worldwide";
    case "countries":
      return loc.countries.join(", ") || "Specific countries";
    case "regions":
      return loc.regions.join(", ") || "Specific regions";
    case "timezone":
      return loc.text ?? "Timezone band";
    default:
      return loc.text ?? "Not stated";
  }
}

export function cleanDisplayTitle(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

export function destinationTitle(value: string, maxLength = 120): string {
  const display = cleanDisplayTitle(value);
  const colon = display.indexOf(":");
  if (display.length > 100 && colon >= 8 && colon <= maxLength) {
    return display
      .slice(0, colon)
      .replace(/[<>:"/\\|?*]/g, "_")
      .replace(/[ .,:;-]+$/g, "");
  }
  const cleaned = display
    .replace(/[<>:"/\\|?*]/g, "_")
    .replace(/[ .,:;-]+$/g, "");
  if (cleaned.length <= maxLength) return cleaned || "Unknown Title";

  const sliced = cleaned.slice(0, maxLength).trimEnd();
  const lastSpace = sliced.lastIndexOf(" ");
  return (lastSpace > 0 ? sliced.slice(0, lastSpace) : sliced)
    .replace(/[ .,:;-]+$/g, "") || "Unknown Title";
}

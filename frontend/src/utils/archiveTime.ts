let displayTimezone: string | undefined;

export function configureArchiveTimezone(timezone?: string | null): void {
  displayTimezone = timezone || undefined;
}

function normalizedUtcValue(value: string): string {
  return /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`;
}

export function formatArchiveTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(normalizedUtcValue(value));
  if (Number.isNaN(date.getTime())) return "-";
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "short",
      timeStyle: "medium",
      timeZone: displayTimezone,
    }).format(date);
  } catch {
    return date.toLocaleString();
  }
}

export function archiveTimezone(): string {
  return displayTimezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
}

import type { TabKey } from "../types/archive";

const TABS: { key: TabKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "pending", label: "Pending review" },
  { key: "needs_metadata", label: "Needs metadata" },
  { key: "approved", label: "Approved" },
  { key: "moved", label: "Moved" },
];

type Props = {
  active: TabKey;
  counts: Record<TabKey, number>;
  onChange: (tab: TabKey) => void;
};

export default function StatusTabs({ active, counts, onChange }: Props) {
  return (
    <div className="status-tabs">
      {TABS.map((t) => (
        <button
          key={t.key}
          className={`status-tabs__tab ${active === t.key ? "status-tabs__tab--active" : ""}`}
          onClick={() => onChange(t.key)}
        >
          {t.label}
          <span className="status-tabs__badge">{counts[t.key]}</span>
        </button>
      ))}
    </div>
  );
}

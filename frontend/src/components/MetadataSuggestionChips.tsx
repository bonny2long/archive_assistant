import type { MetadataCandidate } from "../types/archive";

type Props = {
  label: string;
  field: string;
  candidates: MetadataCandidate[];
  currentValue: string;
  onApply: (value: string) => void;
};

export default function MetadataSuggestionChips({
  label,
  field,
  candidates,
  currentValue,
  onApply,
}: Props) {
  const visible = candidates.filter(
    (candidate) => candidate.field === field && !candidate.ignored,
  );
  if (visible.length === 0) return null;

  return (
    <div className="metadata-suggestions" aria-label={`${label} suggestions`}>
      <span>Suggestions</span>
      <div>
        {visible.map((candidate) => {
          const selected = candidate.value.trim() === currentValue.trim();
          return (
            <button
              type="button"
              className={`metadata-suggestion-chip${selected ? " metadata-suggestion-chip--selected" : ""}`}
              key={`${candidate.source}:${candidate.value}`}
              onClick={() => onApply(candidate.value)}
              title={`Use ${candidate.value} from ${candidate.source_label}`}
            >
              <strong>{candidate.value}</strong>
              <small className="metadata-suggestion-chip__meta">
                {candidate.confidence_label} · {candidate.source_label}
              </small>
            </button>
          );
        })}
      </div>
    </div>
  );
}

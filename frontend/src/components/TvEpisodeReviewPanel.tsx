import type {
  BatchSummary,
  TvEpisode,
  TvEpisodeReviewPatch,
  ReviewItem,
  UnresolvedVideoFile,
  TvWarningDetails,
} from "../types/archive";

type Props = {
  batch: BatchSummary;
  patches: TvEpisodeReviewPatch[];
  onPatchChange: (patches: TvEpisodeReviewPatch[]) => void;
};

function episodeKey(episode: TvEpisode): string {
  return `${episode.source_file}||${episode.relative_source ?? ""}`;
}

function patchKey(patch: TvEpisodeReviewPatch): string {
  return `${patch.source_file}||${patch.relative_source ?? ""}`;
}

function buildDefaultPatch(episode: TvEpisode): TvEpisodeReviewPatch {
  const src = episode.source_file ?? "";
  const isDecimal = /\.\d/.test(src);
  const isSpecialKeyword = /\b(oad|ova|special|oav)\b/i.test(src);

  if (isDecimal) {
    const labelMatch = src.match(/S\d+E\d+\.\d+/i);
    return {
      source_file: episode.source_file,
      relative_source: episode.relative_source ?? null,
      include: true,
      season_number: episode.season_number ?? null,
      episode_number: null,
      is_special: true,
      special_label: labelMatch ? labelMatch[0].toUpperCase() : null,
      destination_group: "season",
      episode_title: episode.episode_title ?? null,
      preserve_source_filename: false,
    };
  }
  if (isSpecialKeyword) {
    return {
      source_file: episode.source_file,
      relative_source: episode.relative_source ?? null,
      include: true,
      season_number: episode.season_number ?? null,
      episode_number: null,
      is_special: true,
      special_label: null,
      destination_group: "specials",
      episode_title: episode.episode_title ?? null,
      preserve_source_filename: false,
    };
  }
  return {
    source_file: episode.source_file,
    relative_source: episode.relative_source ?? null,
    include: true,
    season_number: episode.season_number ?? null,
    episode_number: episode.episode_number ?? null,
    is_special: false,
    special_label: null,
    destination_group: null,
    episode_title: episode.episode_title ?? null,
    preserve_source_filename: false,
  };
}

function getPatch(
  patches: TvEpisodeReviewPatch[],
  episode: TvEpisode,
): TvEpisodeReviewPatch {
  const key = episodeKey(episode);
  const existing = patches.find((p) => patchKey(p) === key);
  return existing ?? buildDefaultPatch(episode);
}

function upsertPatch(
  patches: TvEpisodeReviewPatch[],
  next: TvEpisodeReviewPatch,
): TvEpisodeReviewPatch[] {
  const key = patchKey(next);
  const index = patches.findIndex((p) => patchKey(p) === key);
  if (index >= 0) {
    const updated = [...patches];
    updated[index] = next;
    return updated;
  }
  return [...patches, next];
}

// ── Single episode card ──────────────────────────────────────────────────────

type EpisodeCardProps = {
  episode: TvEpisode;
  blocker: ReviewItem;
  patch: TvEpisodeReviewPatch;
  showTitle: string;
  onChange: (next: TvEpisodeReviewPatch) => void;
};

function EpisodeCard({ episode, blocker, patch, showTitle, onChange }: EpisodeCardProps) {
  const destPreview = (() => {
    if (!patch.include) return "Excluded — will not be moved";
    if (patch.preserve_source_filename) {
      const folder =
        patch.season_number != null
          ? `Season ${String(patch.season_number).padStart(2, "0")}`
          : patch.destination_group === "specials"
          ? "Specials"
          : "?";
      return `TV/Library/${showTitle}/${folder}/${episode.source_file}`;
    }
    if (patch.is_special && patch.special_label) {
      const folder =
        patch.destination_group === "specials" || patch.destination_group === "oad"
          ? "Specials"
          : patch.season_number != null
          ? `Season ${String(patch.season_number).padStart(2, "0")}`
          : "?";
      const title = patch.episode_title ? ` - ${patch.episode_title}` : "";
      const ext = episode.source_file.split(".").pop() ?? "mkv";
      return `TV/Library/${showTitle}/${folder}/${patch.special_label}${title}.${ext}`;
    }
    if (patch.season_number != null && patch.episode_number != null) {
      const code = `S${String(patch.season_number).padStart(2, "0")}E${String(patch.episode_number).padStart(2, "0")}`;
      const folder = `Season ${String(patch.season_number).padStart(2, "0")}`;
      const title = patch.episode_title ? ` - ${patch.episode_title}` : "";
      const ext = episode.source_file.split(".").pop() ?? "mkv";
      return `TV/Library/${showTitle}/${folder}/${code}${title}.${ext}`;
    }
    return "Incomplete — fill in the fields above";
  })();

  return (
    <div className="tv-repair-card">
      <div className="tv-repair-card__header">
        <i className="ti ti-alert-triangle" />
        <span>{blocker.message}</span>
      </div>

      <div className="tv-repair-card__body">
        <div className="tv-repair-card__meta">
          <span className="tv-repair-card__meta-label">Source</span>
          <code className="tv-repair-card__meta-value">{episode.source_file}</code>
          <span className="tv-repair-card__meta-label">Detected</span>
          <code className="tv-repair-card__meta-value">
            {episode.season_number != null ? `Season ${episode.season_number}` : "unknown season"}
            {" · "}
            {episode.episode_number != null ? `Episode ${episode.episode_number}` : "no episode number"}
          </code>
        </div>

        <div className="tv-repair-card__fix">
          <fieldset>
            <legend>Fix</legend>

            <label className="tv-repair-card__radio">
              <input
                type="radio"
                checked={!patch.is_special && patch.include && !patch.preserve_source_filename}
                onChange={() =>
                  onChange({ ...patch, include: true, is_special: false, preserve_source_filename: false })
                }
              />
              Normal episode
            </label>
            {!patch.is_special && patch.include && !patch.preserve_source_filename && (
              <div className="tv-repair-card__fields">
                <label>
                  Season
                  <input
                    type="number"
                    min="1"
                    max="99"
                    value={patch.season_number ?? ""}
                    onChange={(e) =>
                      onChange({ ...patch, season_number: e.target.value ? Number(e.target.value) : null })
                    }
                  />
                </label>
                <label>
                  Episode
                  <input
                    type="number"
                    min="1"
                    max="9999"
                    value={patch.episode_number ?? ""}
                    onChange={(e) =>
                      onChange({ ...patch, episode_number: e.target.value ? Number(e.target.value) : null })
                    }
                  />
                </label>
                <label>
                  Title
                  <input
                    value={patch.episode_title ?? ""}
                    onChange={(e) =>
                      onChange({ ...patch, episode_title: e.target.value || null })
                    }
                  />
                </label>
              </div>
            )}

            <label className="tv-repair-card__radio">
              <input
                type="radio"
                checked={patch.is_special && patch.include}
                onChange={() =>
                  onChange({ ...patch, include: true, is_special: true, preserve_source_filename: false })
                }
              />
              Special / OAD / Extra
            </label>
            {patch.is_special && patch.include && (
              <div className="tv-repair-card__fields">
                <label>
                  Group
                  <select
                    value={patch.destination_group ?? "season"}
                    onChange={(e) =>
                      onChange({
                        ...patch,
                        destination_group: e.target.value as TvEpisodeReviewPatch["destination_group"],
                      })
                    }
                  >
                    <option value="season">Season folder</option>
                    <option value="specials">Specials folder</option>
                    <option value="oad">OAD (→ Specials)</option>
                    <option value="extras">Extras folder</option>
                  </select>
                </label>
                {(patch.destination_group === "season" || patch.destination_group == null) && (
                  <label>
                    Season
                    <input
                      type="number"
                      min="1"
                      max="99"
                      value={patch.season_number ?? ""}
                      onChange={(e) =>
                        onChange({ ...patch, season_number: e.target.value ? Number(e.target.value) : null })
                      }
                    />
                  </label>
                )}
                <label>
                  Label
                  <input
                    placeholder="e.g. S04SP01"
                    value={patch.special_label ?? ""}
                    onChange={(e) =>
                      onChange({ ...patch, special_label: e.target.value || null })
                    }
                  />
                </label>
                <label>
                  Title
                  <input
                    value={patch.episode_title ?? ""}
                    onChange={(e) =>
                      onChange({ ...patch, episode_title: e.target.value || null })
                    }
                  />
                </label>
              </div>
            )}

            <label className="tv-repair-card__radio">
              <input
                type="radio"
                checked={patch.preserve_source_filename && patch.include}
                onChange={() =>
                  onChange({ ...patch, include: true, is_special: false, preserve_source_filename: true })
                }
              />
              Preserve original filename
            </label>
            {patch.preserve_source_filename && patch.include && (
              <div className="tv-repair-card__fields">
                <label>
                  Season
                  <input
                    type="number"
                    min="1"
                    max="99"
                    value={patch.season_number ?? ""}
                    onChange={(e) =>
                      onChange({ ...patch, season_number: e.target.value ? Number(e.target.value) : null })
                    }
                  />
                </label>
              </div>
            )}

            <label className="tv-repair-card__radio">
              <input
                type="radio"
                checked={!patch.include}
                onChange={() => onChange({ ...patch, include: false })}
              />
              Exclude from move
            </label>
          </fieldset>
        </div>
      </div>

      <div className="tv-repair-card__preview">
        <span>Destination preview</span>
        <code>{destPreview}</code>
      </div>
    </div>
  );
}

// ── Duplicate group card ─────────────────────────────────────────────────────

type DuplicateCardProps = {
  episodeCode: string;
  episodes: TvEpisode[];
  patches: TvEpisodeReviewPatch[];
  showTitle: string;
  onChange: (next: TvEpisodeReviewPatch) => void;
};

function DuplicateGroupCard({
  episodeCode,
  episodes,
  patches,
  showTitle,
  onChange,
}: DuplicateCardProps) {
  return (
    <div className="tv-repair-card tv-repair-card--duplicate">
      <div className="tv-repair-card__header">
        <i className="ti ti-copy" />
        <span className="tv-repair-card__type">
          Duplicate episode code: {episodeCode}
        </span>
      </div>
      <p className="tv-repair-card__hint">
        These files share the same episode code. Resolve each one below.
      </p>
      {episodes.map((episode) => {
        const patch = getPatch(patches, episode);
        const blocker: ReviewItem = {
          type: "duplicate_episode_code",
          message: `Duplicate episode code: ${episodeCode}`,
          episode_code: episodeCode,
        };
        return (
          <EpisodeCard
            key={episodeKey(episode)}
            episode={episode}
            blocker={blocker}
            patch={patch}
            showTitle={showTitle}
            onChange={onChange}
          />
        );
      })}
    </div>
  );
}

// ── Special episode card ──────────────────────────────────────────────────────

type SpecialCardProps = {
  episode: TvEpisode;
  patch: TvEpisodeReviewPatch;
  showTitle: string;
  onChange: (next: TvEpisodeReviewPatch) => void;
};

function SpecialEpisodeReviewCard({
  episode,
  patch,
  showTitle,
  onChange,
}: SpecialCardProps) {
  const destPreview = (() => {
    if (!patch.include) return "Excluded — will not be moved";
    const folder = patch.destination_group === "season"
      ? `Season ${String(patch.season_number ?? "").padStart(2, "0")}`
      : patch.destination_group === "oad"
      ? "OADs"
      : patch.destination_group === "ova"
      ? "OVAs"
      : patch.destination_group === "extras"
      ? "Extras"
      : "Specials";
    const label = patch.special_label ?? "";
    const title = patch.episode_title ? ` - ${patch.episode_title}` : "";
    const ext = episode.source_file.split(".").pop() ?? "mkv";
    return `TV/Library/${showTitle}/${folder}/${label}${title}.${ext}`;
  })();

  return (
    <div className="tv-repair-card tv-repair-card--special">
      <div className="tv-repair-card__header">
        <i className="ti ti-disc" />
        <span>Special / OAD / Extra: {episode.source_file}</span>
      </div>
      <div className="tv-repair-card__body">
        <div className="tv-repair-card__meta">
          <span className="tv-repair-card__meta-label">Source</span>
          <code className="tv-repair-card__meta-value">{episode.source_file}</code>
          <span className="tv-repair-card__meta-label">Detected</span>
          <code className="tv-repair-card__meta-value">
            {episode.destination_group ?? "specials"} · {episode.special_label ?? "no label"}
          </code>
        </div>
        <div className="tv-repair-card__fix">
          <fieldset>
            <legend>Configuration</legend>
            <label>
              Group
              <select
                value={patch.destination_group ?? "specials"}
                onChange={(e) =>
                  onChange({
                    ...patch,
                    destination_group: e.target.value as TvEpisodeReviewPatch["destination_group"],
                  })
                }
              >
                <option value="specials">Specials folder</option>
                <option value="season">Season folder</option>
                <option value="oad">OADs folder</option>
                <option value="ova">OVAs folder</option>
                <option value="extras">Extras folder</option>
              </select>
            </label>
            {(patch.destination_group === "season" || patch.destination_group == null) && (
              <label>
                Season
                <input
                  type="number"
                  min="1"
                  max="99"
                  value={patch.season_number ?? ""}
                  onChange={(e) =>
                    onChange({ ...patch, season_number: e.target.value ? Number(e.target.value) : null })
                  }
                />
              </label>
            )}
            <label>
              Label
              <input
                placeholder="e.g. SP01, OADE01"
                value={patch.special_label ?? ""}
                onChange={(e) =>
                  onChange({ ...patch, special_label: e.target.value || null })
                }
              />
            </label>
            <label>
              Title
              <input
                value={patch.episode_title ?? ""}
                onChange={(e) =>
                  onChange({ ...patch, episode_title: e.target.value || null })
                }
              />
            </label>
            <label className="tv-repair-card__radio">
              <input
                type="checkbox"
                checked={!patch.include}
                onChange={() => onChange({ ...patch, include: !patch.include })}
              />
              Exclude from move
            </label>
          </fieldset>
        </div>
      </div>
      <div className="tv-repair-card__preview">
        <span>Destination preview</span>
        <code>{destPreview}</code>
      </div>
    </div>
  );
}

// ── Unresolved video repair card ─────────────────────────────────────────────

type UnresolvedCardProps = {
  file: UnresolvedVideoFile;
  patch: TvEpisodeReviewPatch;
  showTitle: string;
  onChange: (next: TvEpisodeReviewPatch) => void;
};

function UnresolvedVideoRepairCard({
  file,
  patch,
  showTitle,
  onChange,
}: UnresolvedCardProps) {
  const destPreview = (() => {
    if (!patch.include) return "Excluded — will not be moved";
    if (patch.preserve_source_filename) {
      const folder = patch.season_number != null
        ? `Season ${String(patch.season_number).padStart(2, "0")}`
        : "?";
      return `TV/Library/${showTitle}/${folder}/${file.source_file}`;
    }
    if (patch.is_special && patch.special_label) {
      const folder = patch.destination_group === "oad"
        ? "OADs"
        : patch.destination_group === "ova"
        ? "OVAs"
        : patch.destination_group === "extras"
        ? "Extras"
        : "Specials";
      const title = patch.episode_title ? ` - ${patch.episode_title}` : "";
      const ext = file.source_file.split(".").pop() ?? "mkv";
      return `TV/Library/${showTitle}/${folder}/${patch.special_label}${title}.${ext}`;
    }
    if (patch.season_number != null && patch.episode_number != null) {
      const code = `S${String(patch.season_number).padStart(2, "0")}E${String(patch.episode_number).padStart(2, "0")}`;
      const folder = `Season ${String(patch.season_number).padStart(2, "0")}`;
      const title = patch.episode_title ? ` - ${patch.episode_title}` : "";
      const ext = file.source_file.split(".").pop() ?? "mkv";
      return `TV/Library/${showTitle}/${folder}/${code}${title}.${ext}`;
    }
    return "Incomplete — fill in the fields above";
  })();

  return (
    <div className="tv-repair-card tv-repair-card--unresolved">
      <div className="tv-repair-card__header">
        <i className="ti ti-question-mark" />
        <span>Unresolved video: {file.source_file}</span>
      </div>
      <div className="tv-repair-card__body">
        <div className="tv-repair-card__meta">
          <span className="tv-repair-card__meta-label">Source</span>
          <code className="tv-repair-card__meta-value">{file.source_file}</code>
          <span className="tv-repair-card__meta-label">Raw name</span>
          <code className="tv-repair-card__meta-value">{file.raw_name ?? file.source_file}</code>
        </div>
        <div className="tv-repair-card__fix">
          <fieldset>
            <legend>Classify as</legend>

            <label className="tv-repair-card__radio">
              <input
                type="radio"
                checked={!patch.is_special && patch.include && !patch.preserve_source_filename && !patch.preserve_source_filename}
                onChange={() =>
                  onChange({ ...patch, include: true, is_special: false, preserve_source_filename: false })
                }
              />
              Normal episode
            </label>
            {!patch.is_special && patch.include && !patch.preserve_source_filename && (
              <div className="tv-repair-card__fields">
                <label>
                  Season
                  <input
                    type="number"
                    min="1"
                    max="99"
                    value={patch.season_number ?? ""}
                    onChange={(e) =>
                      onChange({ ...patch, season_number: e.target.value ? Number(e.target.value) : null })
                    }
                  />
                </label>
                <label>
                  Episode
                  <input
                    type="number"
                    min="1"
                    max="9999"
                    value={patch.episode_number ?? ""}
                    onChange={(e) =>
                      onChange({ ...patch, episode_number: e.target.value ? Number(e.target.value) : null })
                    }
                  />
                </label>
                <label>
                  Title
                  <input
                    value={patch.episode_title ?? ""}
                    onChange={(e) =>
                      onChange({ ...patch, episode_title: e.target.value || null })
                    }
                  />
                </label>
              </div>
            )}

            <label className="tv-repair-card__radio">
              <input
                type="radio"
                checked={patch.is_special && patch.include}
                onChange={() =>
                  onChange({ ...patch, include: true, is_special: true, preserve_source_filename: false })
                }
              />
              Special / OAD / Extra
            </label>
            {patch.is_special && patch.include && (
              <div className="tv-repair-card__fields">
                <label>
                  Group
                  <select
                    value={patch.destination_group ?? "specials"}
                    onChange={(e) =>
                      onChange({
                        ...patch,
                        destination_group: e.target.value as TvEpisodeReviewPatch["destination_group"],
                      })
                    }
                  >
                    <option value="specials">Specials folder</option>
                    <option value="oad">OADs folder</option>
                    <option value="ova">OVAs folder</option>
                    <option value="extras">Extras folder</option>
                    <option value="season">Season folder</option>
                  </select>
                </label>
                {(patch.destination_group === "season" || patch.destination_group == null) && (
                  <label>
                    Season
                    <input
                      type="number"
                      min="1"
                      max="99"
                      value={patch.season_number ?? ""}
                      onChange={(e) =>
                        onChange({ ...patch, season_number: e.target.value ? Number(e.target.value) : null })
                      }
                    />
                  </label>
                )}
                <label>
                  Label
                  <input
                    placeholder="e.g. SP01, OADE01"
                    value={patch.special_label ?? ""}
                    onChange={(e) =>
                      onChange({ ...patch, special_label: e.target.value || null })
                    }
                  />
                </label>
                <label>
                  Title
                  <input
                    value={patch.episode_title ?? ""}
                    onChange={(e) =>
                      onChange({ ...patch, episode_title: e.target.value || null })
                    }
                  />
                </label>
              </div>
            )}

            <label className="tv-repair-card__radio">
              <input
                type="radio"
                checked={patch.preserve_source_filename && patch.include}
                onChange={() =>
                  onChange({ ...patch, include: true, is_special: false, preserve_source_filename: true })
                }
              />
              Preserve original filename
            </label>
            {patch.preserve_source_filename && patch.include && (
              <div className="tv-repair-card__fields">
                <label>
                  Season
                  <input
                    type="number"
                    min="1"
                    max="99"
                    value={patch.season_number ?? ""}
                    onChange={(e) =>
                      onChange({ ...patch, season_number: e.target.value ? Number(e.target.value) : null })
                    }
                  />
                </label>
              </div>
            )}

            <label className="tv-repair-card__radio">
              <input
                type="radio"
                checked={!patch.include}
                onChange={() => onChange({ ...patch, include: false })}
              />
              Exclude from move
            </label>
          </fieldset>
        </div>
      </div>
      <div className="tv-repair-card__preview">
        <span>Destination preview</span>
        <code>{destPreview}</code>
      </div>
    </div>
  );
}

// ── Warning details panel ─────────────────────────────────────────────────────

type WarningPanelProps = {
  details: TvWarningDetails | null | undefined;
};

function WarningDetailsPanel({ details }: WarningPanelProps) {
  if (!details) return null;
  const { unparsed_video_files, generic_title_files } = details;
  const hasAny =
    (unparsed_video_files?.length ?? 0) > 0 ||
    (generic_title_files?.length ?? 0) > 0;
  if (!hasAny) return null;

  return (
    <div className="tv-review-panel__warnings tv-review-panel__warnings--details">
      <span>Warning details</span>

      {(unparsed_video_files?.length ?? 0) > 0 && (
        <details>
          <summary>
            <i className="ti ti-file-unknown" /> Unparsed video files ({unparsed_video_files.length})
          </summary>
          <ul className="tv-warning-file-list">
            {unparsed_video_files.map((f, i) => (
              <li key={i}>
                <code>{f.source_file}</code>
                <small>{f.relative_source ?? ""}</small>
              </li>
            ))}
          </ul>
        </details>
      )}

      {(generic_title_files?.length ?? 0) > 0 && (
        <details>
          <summary>
            <i className="ti ti-file-text" /> Files with generic titles ({generic_title_files.length})
          </summary>
          <ul className="tv-warning-file-list">
            {generic_title_files.map((f, i) => (
              <li key={i}>
                <code>{f.source_file}</code>
                <small>{f.relative_source ?? ""}</small>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

// ── Main export ──────────────────────────────────────────────────────────────

export default function TvEpisodeReviewPanel({
  batch,
  patches,
  onPatchChange,
}: Props) {
  const allEpisodes = batch.seasons.flatMap((s) => s.episodes);
  const specialEpisodes = batch.special_episodes ?? [];
  const unresolvedFiles = batch.unresolved_video_files ?? [];
  const warningDetails = batch.tv_warning_details ?? null;
  const blockingItems = batch.blocking_review_items ?? [];
  const nonBlockingItems = batch.non_blocking_review_items ?? [];

  // Collect missing-episode-number blockers (keyed by file_name)
  const missingEpBlockers = blockingItems.filter(
    (item) => item.type === "missing_episode_number" || item.type === "missing_season_number",
  );
  const missingEpFiles = new Set(missingEpBlockers.map((i) => i.file_name).filter(Boolean));

  // Collect duplicate code blockers
  const duplicateCodes = blockingItems
    .filter((item) => item.type === "duplicate_episode_code")
    .map((item) => item.episode_code)
    .filter((code): code is string => Boolean(code));
  const uniqueDuplicateCodes = [...new Set(duplicateCodes)];

  // Files that are already covered by a duplicate group — don't double-show them
  const duplicateGroupFiles = new Set(
    uniqueDuplicateCodes.flatMap((code) =>
      allEpisodes
        .filter((ep) => ep.episode_code === code)
        .map((ep) => ep.source_file),
    ),
  );

  const missingEpEpisodes = allEpisodes.filter(
    (ep) => missingEpFiles.has(ep.source_file) && !duplicateGroupFiles.has(ep.source_file),
  );

  // Build default patch for special episodes
  function defaultSpecialPatch(ep: TvEpisode): TvEpisodeReviewPatch {
    return {
      source_file: ep.source_file,
      relative_source: ep.relative_source ?? null,
      include: true,
      season_number: ep.season_number ?? null,
      episode_number: null,
      is_special: true,
      special_label: ep.special_label ?? null,
      destination_group: (ep.destination_group ?? "specials") as TvEpisodeReviewPatch["destination_group"],
      episode_title: ep.episode_title ?? null,
      preserve_source_filename: false,
    };
  }

  // Build default patch for unresolved files
  function defaultUnresolvedPatch(file: UnresolvedVideoFile): TvEpisodeReviewPatch {
    return {
      source_file: file.source_file,
      relative_source: file.relative_source ?? null,
      include: true,
      season_number: null,
      episode_number: null,
      is_special: false,
      special_label: null,
      destination_group: null,
      episode_title: null,
      preserve_source_filename: false,
    };
  }

  const handlePatchChange = (next: TvEpisodeReviewPatch) => {
    onPatchChange(upsertPatch(patches, next));
  };

  const showTitle = batch.show_title ?? "Unknown Show";
  const hasBlockers = blockingItems.length > 0;
  const hasAnyContent = hasBlockers || nonBlockingItems.length > 0 ||
    specialEpisodes.length > 0 || unresolvedFiles.length > 0 ||
    (warningDetails?.unparsed_video_files?.length ?? 0) > 0 ||
    (warningDetails?.generic_title_files?.length ?? 0) > 0;

  if (!hasAnyContent) {
    return null;
  }

  return (
    <section className="tv-review-panel">
      <div className="tv-review-panel__summary">
        <strong>
          {blockingItems.length} blocking item{blockingItems.length !== 1 ? "s" : ""} ·{" "}
          {nonBlockingItems.length} warning{nonBlockingItems.length !== 1 ? "s" : ""}
        </strong>
      </div>

      {/* ── Section 1: Fix Required (blocking items with repair cards) ── */}
      <div className="tv-review-panel__section">
        {missingEpEpisodes.map((episode) => {
          const blocker =
            missingEpBlockers.find((b) => b.file_name === episode.source_file) ??
            missingEpBlockers[0];
          return (
            <EpisodeCard
              key={episodeKey(episode)}
              episode={episode}
              blocker={blocker}
              patch={getPatch(patches, episode)}
              showTitle={showTitle}
              onChange={handlePatchChange}
            />
          );
        })}

        {/* Duplicate episode code groups */}
        {uniqueDuplicateCodes.map((code) => {
          const groupEpisodes = allEpisodes.filter((ep) => ep.episode_code === code);
          return (
            <DuplicateGroupCard
              key={code}
              episodeCode={code}
              episodes={groupEpisodes}
              patches={patches}
              showTitle={showTitle}
              onChange={handlePatchChange}
            />
          );
        })}
      </div>

      {/* ── Section 2: Specials / OADs / Extras ── */}
      {specialEpisodes.length > 0 && (
        <div className="tv-review-panel__section">
          <h4 className="tv-review-panel__section-title">
            <i className="ti ti-disc" /> Specials / OADs / OVAs ({specialEpisodes.length})
          </h4>
          {specialEpisodes.map((ep) => {
            const key = `${ep.source_file}||${ep.relative_source ?? ""}`;
            const existing = patches.find(
              (p) => p.source_file === ep.source_file && (p.relative_source ?? "") === (ep.relative_source ?? ""),
            );
            const patch = existing ?? defaultSpecialPatch(ep);
            return (
              <SpecialEpisodeReviewCard
                key={key}
                episode={ep}
                patch={patch}
                showTitle={showTitle}
                onChange={handlePatchChange}
              />
            );
          })}
        </div>
      )}

      {/* ── Section 3: Unresolved Videos ── */}
      {unresolvedFiles.length > 0 && (
        <div className="tv-review-panel__section">
          <h4 className="tv-review-panel__section-title">
            <i className="ti ti-question-mark" /> Unresolved videos ({unresolvedFiles.length})
          </h4>
          {unresolvedFiles.map((file) => {
            const key = `${file.source_file}||${file.relative_source ?? ""}`;
            const existing = patches.find(
              (p) => p.source_file === file.source_file && (p.relative_source ?? "") === (file.relative_source ?? ""),
            );
            const patch = existing ?? defaultUnresolvedPatch(file);
            return (
              <UnresolvedVideoRepairCard
                key={key}
                file={file}
                patch={patch}
                showTitle={showTitle}
                onChange={handlePatchChange}
              />
            );
          })}
        </div>
      )}

      {/* ── Section 4: Warnings ── */}
      {nonBlockingItems.length > 0 && (
        <div className="tv-review-panel__warnings">
          <span>Warnings</span>
          {nonBlockingItems.map((item, index) => (
            <p key={`${item.type}-${item.file_name ?? index}`} className="tv-review-panel__warning-row">
              <i className="ti ti-info-circle" /> {item.message}
              {item.file_name && <small>{item.file_name}</small>}
            </p>
          ))}
        </div>
      )}

      {/* Warning details panel (per-file breakdown) */}
      <WarningDetailsPanel details={warningDetails} />

    </section>
  );
}

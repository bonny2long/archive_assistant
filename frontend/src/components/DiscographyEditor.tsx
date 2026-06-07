import { useMemo, useState } from "react";
import type { BatchSummary, DiscographyMetadataUpdate } from "../types/archive";

type Props = {
  batch: BatchSummary;
  saving: boolean;
  onSave: (update: DiscographyMetadataUpdate) => Promise<void>;
  onClose: () => void;
};

function sanitizePathPart(value: string): string {
  return value.replace(/[<>:"/\\|?*]/g, "_").trim();
}

export default function DiscographyEditor({
  batch,
  saving,
  onSave,
  onClose,
}: Props) {
  const [artist, setArtist] = useState(
    () => batch.suggested_metadata?.artist ?? batch.artist ?? "",
  );
  const destination = useMemo(
    () => `Music/Discographies/${sanitizePathPart(artist)}`,
    [artist],
  );
  const valid = artist.trim().length > 0;

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form
        className="metadata-editor"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (valid) void onSave({ artist: artist.trim() });
        }}
      >
        <div className="metadata-editor__header">
          <div>
            <h2>Correct discography</h2>
            <p>Update the collection artist without changing embedded track tags.</p>
          </div>
          <button type="button" className="btn-sm" disabled={saving} onClick={onClose}>
            <i className="ti ti-x" />
          </button>
        </div>
        <label>
          <span>Artist</span>
          <input value={artist} autoFocus onChange={(event) => setArtist(event.target.value)} />
        </label>
        <div className="metadata-editor__preview">
          <span>Collection type</span>
          <strong>Discography</strong>
          <div><small>Destination preview</small><code>{destination}</code></div>
        </div>
        <div className="metadata-editor__actions">
          <button type="button" className="btn" disabled={saving} onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn--green" disabled={saving || !valid}>
            <i className={`ti ti-${saving ? "loader-2 spinner" : "device-floppy"}`} />
            Save
          </button>
        </div>
      </form>
    </div>
  );
}

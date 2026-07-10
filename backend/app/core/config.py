from pathlib import Path
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Archive Assistant"
    debug: bool = True

    # Project root is two levels above backend/app/core/config.py
    backend_dir: Path = Path(__file__).resolve().parents[2]
    project_root: Path = backend_dir.parent
    data_root: Path = project_root / "data"

    ingest_root: Path = data_root / "_INGEST"
    reports_dir: Path = data_root / "_REPORTS" / "archive-assistant" / "ingest-reports"
    move_logs_dir: Path = data_root / "_REPORTS" / "archive-assistant" / "move-logs"
    music_flac_dir: Path = data_root / "Music" / "Library" / "FLAC"
    music_mp3_dir: Path = data_root / "Music" / "Library" / "MP3"
    music_discographies_dir: Path = data_root / "Music" / "Discographies"
    music_metadata_dir: Path = data_root / "Music" / "Metadata"
    movies_dir: Path = data_root / "Movies" / "Library"
    movies_metadata_dir: Path = data_root / "Movies" / "Metadata"
    tv_dir: Path = data_root / "TV" / "Library"
    tv_metadata_dir: Path = data_root / "TV" / "Metadata"
    books_dir: Path = data_root / "Books"
    books_metadata_dir: Path = data_root / "Books" / "Metadata"
    audiobooks_dir: Path = data_root / "Audiobooks" / "Library"
    audiobooks_metadata_dir: Path = data_root / "Audiobooks" / "Metadata"
    quarantine_discography_dir: Path = (
        data_root / "_QUARANTINE" / "music" / "discography-excluded"
    )
    quarantine_unknown_dir: Path = data_root / "_QUARANTINE" / "unknown-type"
    quarantine_unsupported_dir: Path = data_root / "_QUARANTINE" / "unsupported-file"
    quarantine_reports_dir: Path = (
        data_root / "_REPORTS" / "archive-assistant" / "quarantine-reports"
    )

    database_url: str = f"sqlite:///{backend_dir / 'archive_assistant.db'}"

    api_docs_enabled: bool = False
    dev_tools_enabled: bool = True
    archive_assistant_timezone: str = "America/Chicago"

    musicbrainz_api_base_url: str = "https://musicbrainz.org/ws/2"
    musicbrainz_user_agent: str = "ArchiveAssistant/0.1 (local metadata enrichment)"
    musicbrainz_timeout_seconds: float = 15.0

    class Config:
        env_file = ".env"

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_environment(cls, value):
        """Accept common environment labels while retaining a boolean setting."""
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in {"release", "production", "prod"}:
                return False
            if normalized in {"development", "dev"}:
                return True
        return value

    @model_validator(mode="after")
    def derive_data_root_paths(self):
        provided = self.model_fields_set
        derived_paths = {
            "ingest_root": self.data_root / "_INGEST",
            "reports_dir": (
                self.data_root / "_REPORTS" / "archive-assistant" / "ingest-reports"
            ),
            "move_logs_dir": (
                self.data_root / "_REPORTS" / "archive-assistant" / "move-logs"
            ),
            "music_flac_dir": self.data_root / "Music" / "Library" / "FLAC",
            "music_mp3_dir": self.data_root / "Music" / "Library" / "MP3",
            "music_discographies_dir": self.data_root / "Music" / "Discographies",
            "music_metadata_dir": self.data_root / "Music" / "Metadata",
            "movies_dir": self.data_root / "Movies" / "Library",
            "movies_metadata_dir": self.data_root / "Movies" / "Metadata",
            "tv_dir": self.data_root / "TV" / "Library",
            "tv_metadata_dir": self.data_root / "TV" / "Metadata",
            "books_dir": self.data_root / "Books",
            "books_metadata_dir": self.data_root / "Books" / "Metadata",
            "audiobooks_dir": self.data_root / "Audiobooks" / "Library",
            "audiobooks_metadata_dir": self.data_root / "Audiobooks" / "Metadata",
            "quarantine_discography_dir": (
                self.data_root / "_QUARANTINE" / "music" / "discography-excluded"
            ),
            "quarantine_unknown_dir": self.data_root / "_QUARANTINE" / "unknown-type",
            "quarantine_unsupported_dir": (
                self.data_root / "_QUARANTINE" / "unsupported-file"
            ),
            "quarantine_reports_dir": (
                self.data_root
                / "_REPORTS"
                / "archive-assistant"
                / "quarantine-reports"
            ),
        }
        for field_name, value in derived_paths.items():
            if field_name not in provided:
                setattr(self, field_name, value)
        return self


settings = Settings()

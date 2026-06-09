from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Archive Assistant"
    debug: bool = True

    # Project root is two levels above backend/app/core/config.py
    backend_dir: Path = Path(__file__).resolve().parents[2]
    project_root: Path = backend_dir.parent
    data_root: Path = project_root / "data"

    ingest_root: Path = data_root / "_INGEST"
    reports_dir: Path = data_root / "_REPORTS" / "ingest-reports"
    move_logs_dir: Path = data_root / "_REPORTS" / "move-logs"
    music_flac_dir: Path = data_root / "Music" / "Library" / "FLAC"
    music_mp3_dir: Path = data_root / "Music" / "Library" / "MP3"
    music_discographies_dir: Path = data_root / "Music" / "Discographies"
    movies_dir: Path = data_root / "Movies" / "Library"
    movies_metadata_dir: Path = data_root / "Movies" / "Metadata"
    tv_dir: Path = data_root / "TV" / "Library"
    tv_metadata_dir: Path = data_root / "TV" / "Metadata"
    books_dir: Path = data_root / "Books"
    audiobooks_dir: Path = data_root / "Audiobooks" / "Library"
    quarantine_discography_dir: Path = (
        data_root / "_QUARANTINE" / "music" / "discography-excluded"
    )
    quarantine_unknown_dir: Path = data_root / "_QUARANTINE" / "unknown-type"
    quarantine_unsupported_dir: Path = data_root / "_QUARANTINE" / "unsupported-file"
    quarantine_reports_dir: Path = data_root / "_REPORTS" / "quarantine-reports"

    database_url: str = f"sqlite:///{backend_dir / 'archive_assistant.db'}"

    api_docs_enabled: bool = False
    dev_tools_enabled: bool = True
    archive_assistant_timezone: str = "America/Chicago"

    class Config:
        env_file = ".env"


settings = Settings()

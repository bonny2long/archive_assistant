from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Archive Assistant"
    debug: bool = True

    # Project root is two levels above backend/app/core/config.py
    backend_dir: Path = Path(__file__).resolve().parents[2]
    project_root: Path = backend_dir.parent
    data_root: Path = project_root / "data"

    ingest_music_dir: Path = data_root / "_INGEST" / "music"
    reports_dir: Path = data_root / "_REPORTS" / "ingest-reports"
    move_logs_dir: Path = data_root / "_REPORTS" / "move-logs"
    music_flac_dir: Path = data_root / "Music" / "Library" / "FLAC"
    music_mp3_dir: Path = data_root / "Music" / "Library" / "MP3"
    music_discographies_dir: Path = data_root / "Music" / "Discographies"

    database_url: str = f"sqlite:///{backend_dir / 'archive_assistant.db'}"

    api_docs_enabled: bool = False
    dev_tools_enabled: bool = True

    class Config:
        env_file = ".env"


settings = Settings()

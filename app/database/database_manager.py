"""Database location selection."""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DatabaseLocation(Enum):
    LOCAL_DISK = "local_disk"
    FTP = "ftp"


@dataclass
class DatabaseManager:
    """Defines where the shared root database is stored."""

    location: DatabaseLocation = DatabaseLocation.LOCAL_DISK
    local_path: Optional[str] = None
    ftp_path: Optional[str] = None

    def set_local_path(self, path: str) -> None:
        self.location = DatabaseLocation.LOCAL_DISK
        self.local_path = path

    def set_ftp_path(self, path: str) -> None:
        self.location = DatabaseLocation.FTP
        self.ftp_path = path

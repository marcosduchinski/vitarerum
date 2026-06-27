import os
import tempfile
from pathlib import Path

from anyio import to_thread


class LocalDiskFileStorage:
    """Persists uploaded file bytes under a base data directory.

    The ``file_reference`` is the path *relative* to the base directory — callers
    build it with readable subfolders (e.g. ``proposals/<id>/<uuid>_<name>``).
    Reads are confined to the base directory to prevent path traversal.

    Blocking filesystem work runs in a worker thread so it never stalls the event
    loop. Writes go to a temporary file and are atomically renamed into place, so
    a crash mid-write never leaves a half-written destination; the temp file is
    removed if the write fails.
    """

    def __init__(self, data_dir: Path) -> None:
        self._base = data_dir.resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    def _resolve(self, file_reference: str) -> Path:
        dest = (self._base / file_reference).resolve()
        if not dest.is_relative_to(self._base):
            raise FileNotFoundError(file_reference)
        return dest

    async def save(self, content: bytes, filename: str) -> str:
        dest = self._resolve(filename)
        await to_thread.run_sync(self._write_atomic, dest, content)
        return filename

    @staticmethod
    def _write_atomic(dest: Path, content: bytes) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            os.replace(tmp, dest)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    async def read(self, file_reference: str) -> bytes:
        dest = self._resolve(file_reference)
        try:
            return await to_thread.run_sync(dest.read_bytes)
        except (FileNotFoundError, IsADirectoryError) as exc:
            raise FileNotFoundError(file_reference) from exc

    async def delete(self, file_reference: str) -> None:
        dest = self._resolve(file_reference)
        await to_thread.run_sync(self._unlink_quietly, dest)

    @staticmethod
    def _unlink_quietly(dest: Path) -> None:
        try:
            dest.unlink()
        except FileNotFoundError:
            pass

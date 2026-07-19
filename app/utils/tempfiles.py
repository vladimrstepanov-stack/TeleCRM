"""Работа с временными файлами голоса и документов."""

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def temp_path(suffix: str) -> Iterator[Path]:
    """Отдаёт путь к временному файлу и гарантированно удаляет его после блока."""
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    handle.close()
    path = Path(handle.name)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)

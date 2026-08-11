"""Shared plumbing for rendering MUHNAC's .docx forms with docxtpl.

The templates under ``templates/`` are the museum's own blank forms with Jinja
placeholders written into their cells by ``scripts/build_form_templates.py``;
nothing about their layout is reproduced in code, so a revised form only needs
that script re-run.
"""

from __future__ import annotations

from functools import cache
from io import BytesIO
from pathlib import Path
from typing import Any

from anyio.to_thread import run_sync
from docxtpl import DocxTemplate

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

TEMPLATE_DIR = Path(__file__).parent / "templates"

# The forms print dates day-first.
DATE_FORMAT = "%d-%m-%Y"


@cache
def _template_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


def _render(template_path: Path, context: dict[str, Any]) -> bytes:
    template = DocxTemplate(BytesIO(_template_bytes(str(template_path))))
    template.render(context)
    rendered = BytesIO()
    template.save(rendered)
    return rendered.getvalue()


async def render_form(template_path: Path, context: dict[str, Any]) -> bytes:
    """Fill a form template off the event loop.

    python-docx parses the whole package on every render — the access register
    carries ~2 MB of embedded fonts — which is far too slow to do inline.
    """
    return await run_sync(_render, template_path, context)

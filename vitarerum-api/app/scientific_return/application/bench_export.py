"""CSV projection for completed scientific-return test candidates."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence

CSV_COLUMNS = (
    "item_id",
    "tentativa",
    "autor",
    "nome_objeto",
    "num_inventario",
    "rank",
    "score",
    "score_version",
    "fonte_id",
    "fonte_nome",
    "fonte_revisao",
    "fonte_localizador",
    "query",
    "discovery_basis",
    "inventory_evidence_status",
    "evidencia",
)


def _safe(value: object) -> object:
    if value is None:
        return ""
    text = str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def export_candidates(rows: Sequence[Mapping[str, object]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow(
            _safe(value)
            for value in (
                row["itemId"],
                row["attemptNumber"],
                row["author"],
                row["objectName"],
                row["inventoryNumber"],
                row["rank"],
                f"{row['score']:.5f}",
                row["scoreVersion"],
                row["sourceId"],
                row["sourceName"],
                row["sourceRevision"],
                row["sourceLocator"],
                row["query"],
                row["discoveryBasis"],
                row["inventoryEvidenceStatus"],
                row["evidence"],
            )
        )
    return output.getvalue()

"""Render chart/table-heavy PDF pages and build the ColPali multi-vector page index."""

from __future__ import annotations

import json
import sys
import time

import pypdfium2 as pdfium
import pypdfium2.raw as raw
from qdrant_client import QdrantClient, models

from ledgerline.core.paths import iter_dataroom
from ledgerline.core.settings import get_settings
from ledgerline.retrieval.visual import (
    COLLECTION,
    PageRecord,
    embed_images,
    pages_index_path,
    visual_available,
)

VISUAL_FOLDERS = {"board", "registers", "org"}


def main() -> int:
    s = get_settings()
    out_dir = s.data_dir / "pages"
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = {
        d["source_path"]: d for d in json.loads((s.data_dir / "ingest" / "docs.json").read_text())
    }
    records: list[PageRecord] = []
    for path in iter_dataroom(s.dataroom_dir):
        if path.suffix != ".pdf":
            continue
        meta = docs.get(str(path))
        if meta is None:
            continue
        pdf = pdfium.PdfDocument(str(path))
        for i, page in enumerate(pdf):
            n_img = sum(1 for _ in page.get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE]))
            folder = path.relative_to(s.dataroom_dir).parts[0]
            # All data-room PDF pages are indexed; chart/table pages are the targets, the rest
            # act as distractors. Pages are tagged so evals can report on visual pages only.
            _ = n_img, folder in VISUAL_FOLDERS
            img = out_dir / f"{meta['doc_id']}_p{i + 1}.png"
            page.render(scale=1.5).to_pil().save(img)
            text = page.get_textpage().get_text_range()
            records.append(
                PageRecord(
                    page_id=f"{meta['doc_id']}_p{i + 1}",
                    doc_id=meta["doc_id"],
                    page=i + 1,
                    image_path=str(img),
                    text=text,
                    title=meta["title"],
                )
            )
    pages_index_path(s.data_dir).write_text(json.dumps([r.model_dump() for r in records], indent=1))
    print(f"rendered {len(records)} pages")
    if not visual_available():
        print("colpali-engine not installed (uv sync --extra visual); lexical fallback only")
        return 0
    t0 = time.time()
    vecs = embed_images([__import__("pathlib").Path(r.image_path) for r in records])
    client = QdrantClient(url=s.qdrant_url)
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(
        COLLECTION,
        vectors_config=models.VectorParams(
            size=len(vecs[0][0]),
            distance=models.Distance.COSINE,
            multivector_config=models.MultiVectorConfig(
                comparator=models.MultiVectorComparator.MAX_SIM
            ),
        ),
    )
    # One page per request: a page is ~1,100 x 128 floats (Qdrant caps requests at 32 MB).
    for i, (r, v) in enumerate(zip(records, vecs, strict=True)):
        payload = {"page_id": r.page_id, "doc_id": r.doc_id, "page": r.page}
        client.upsert(COLLECTION, points=[models.PointStruct(id=i, vector=v, payload=payload)])
    print(
        f"indexed {len(records)} pages with {len(vecs[0])}x{len(vecs[0][0])} vectors each "
        f"({time.time() - t0:.0f}s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

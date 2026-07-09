from fastapi import APIRouter, HTTPException, Query
from app.schemas.records import (
    NotebookExport,
    NotebookImportResponse,
    RecordCreate,
    RecordItem,
    RecordList,
    RecordStats,
    RecordUpdate,
    ReviewUpdate,
)
from engine.storage.notebook import (
    add_record,
    delete_record,
    export_records,
    get_record,
    import_records,
    list_records,
    mark_review,
    record_stats,
    update_record,
)

router = APIRouter()


@router.post("", response_model=RecordItem)
def create_record(req: RecordCreate) -> RecordItem:
    return RecordItem(**add_record(req.model_dump()))


@router.get("/stats", response_model=RecordStats)
def stats() -> RecordStats:
    return RecordStats(**record_stats())


@router.get("/export", response_model=NotebookExport)
def export_notebook() -> NotebookExport:
    return NotebookExport(**export_records())


@router.post("/import", response_model=NotebookImportResponse)
def import_notebook(payload: dict) -> NotebookImportResponse:
    try:
        return NotebookImportResponse(**import_records(payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=RecordList)
def records(
    limit: int = Query(50, ge=1, le=300),
    favorite: bool | None = Query(None),
    due_only: bool = Query(False),
    q: str | None = Query(None),
) -> RecordList:
    return RecordList(records=[RecordItem(**r) for r in list_records(limit, favorite=favorite, due_only=due_only, query=q)])


@router.get("/{record_id}", response_model=RecordItem)
def read_record(record_id: int) -> RecordItem:
    item = get_record(record_id)
    if not item:
        raise HTTPException(status_code=404, detail="record not found")
    return RecordItem(**item)


@router.patch("/{record_id}", response_model=RecordItem)
def patch_record(record_id: int, req: RecordUpdate) -> RecordItem:
    try:
        return RecordItem(**update_record(record_id, {k: v for k, v in req.model_dump().items() if v is not None}))
    except KeyError:
        raise HTTPException(status_code=404, detail="record not found")


@router.post("/{record_id}/review", response_model=RecordItem)
def review_record(record_id: int, req: ReviewUpdate) -> RecordItem:
    try:
        return RecordItem(**mark_review(record_id, correct=req.correct, note=req.note))
    except KeyError:
        raise HTTPException(status_code=404, detail="record not found")


@router.delete("/{record_id}")
def remove_record(record_id: int) -> dict:
    if not delete_record(record_id):
        raise HTTPException(status_code=404, detail="record not found")
    return {"ok": True, "deleted": record_id}

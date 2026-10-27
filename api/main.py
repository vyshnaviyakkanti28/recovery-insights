"""HTTP API for recovery insights.

Run locally:
    uvicorn api.main:app --reload

Then open http://127.0.0.1:8000/docs to try it in the browser.
"""

from __future__ import annotations

import shutil
import tempfile
from xml.etree.ElementTree import ParseError

from fastapi import FastAPI, File, HTTPException, UploadFile

from recovery import analyze, parse_export

app = FastAPI(
    title="Recovery Insights API",
    description="Upload an Apple Health export and get a daily recovery score with trends.",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/analyze")
def analyze_export(file: UploadFile = File(...)) -> dict:
    """Analyze an uploaded export.xml.

    The upload is spooled to a temporary file on disk instead of being read
    into memory, because real exports are often hundreds of megabytes.
    """
    if not (file.filename or "").lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="Upload the export.xml file from your Health export.")

    with tempfile.NamedTemporaryFile(suffix=".xml") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp.flush()
        try:
            days = parse_export(tmp.name)
        except ParseError as exc:
            raise HTTPException(status_code=422, detail=f"Not a valid Health export: {exc}") from exc

    if not days:
        raise HTTPException(status_code=422, detail="No sleep, heart rate, HRV, or step records found.")

    return analyze(days)

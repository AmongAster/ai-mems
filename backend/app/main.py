import os
import mimetypes
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from pathlib import Path
import shutil

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ai import generate_meme_image
from .db import Base, engine, get_db
from .import_storage import import_from_storage_dir
from .models import Meme
from .settings import settings


app = FastAPI(
    title=settings.app_name,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/swagger", include_in_schema=False)
def swagger_alias():
    return RedirectResponse(url="/docs")

# dev-friendly CORS (чтобы фронт мог дергать API с другого порта)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ensure_storage_dir() -> Path:
    p = Path(settings.storage_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ensure_db():
    # На случай запуска без lifecycle hooks (например, некоторые тестовые клиенты)
    Base.metadata.create_all(bind=engine)


def _meme_response(meme: Meme) -> dict:
    return {
        "id": meme.id,
        "caption": meme.caption,
        "source": meme.source,
        "filename": meme.filename,
        "image_url": f"/memes/{meme.id}/image",
    }


def _save_meme_bytes(
    db: Session,
    *,
    data: bytes,
    content_type: str,
    caption: str | None,
    source: str,
    preferred_ext: str | None = None,
) -> dict:
    storage = _ensure_storage_dir()
    ext = (preferred_ext or mimetypes.guess_extension(content_type) or ".img").lower()
    if ext == ".jpe":
        ext = ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    (storage / filename).write_bytes(data)
    meme = Meme(
        caption=caption,
        filename=filename,
        content_type=content_type,
        source=source,
    )
    db.add(meme)
    db.commit()
    db.refresh(meme)
    return _meme_response(meme)


def _telegram_api_get(method: str, **query: str) -> dict:
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=400, detail="TELEGRAM_BOT_TOKEN is not configured")
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
    if query:
        url = f"{url}?{urlencode(query)}"
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=20) as resp:
            payload = resp.read().decode("utf-8")
    except (HTTPError, URLError) as e:
        raise HTTPException(status_code=502, detail=f"telegram api error: {e}") from e
    import json

    data = json.loads(payload)
    if not data.get("ok"):
        raise HTTPException(status_code=502, detail=f"telegram api rejected request: {data}")
    return data


def _telegram_download_file(file_path: str) -> tuple[bytes, str]:
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=400, detail="TELEGRAM_BOT_TOKEN is not configured")
    url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=30) as resp:
            data = resp.read()
            content_type = resp.headers.get_content_type() or "application/octet-stream"
    except (HTTPError, URLError) as e:
        raise HTTPException(status_code=502, detail=f"telegram file download failed: {e}") from e
    return data, content_type


def _extract_latest_telegram_image_message(updates: list[dict]) -> dict | None:
    wanted_chat_id = str(settings.telegram_chat_id).strip() if settings.telegram_chat_id else None
    for upd in reversed(updates):
        msg = upd.get("message") or upd.get("channel_post")
        if not isinstance(msg, dict):
            continue
        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id", "")).strip()
        if wanted_chat_id and chat_id != wanted_chat_id:
            continue
        if msg.get("photo"):
            return msg
        doc = msg.get("document") or {}
        mime = str(doc.get("mime_type", ""))
        if mime.startswith("image/"):
            return msg
    return None


def _require_ingest_token(x_telegram_token: str | None):
    expected = (settings.telegram_ingest_token or "").strip()
    if not expected:
        return
    got = (x_telegram_token or "").strip()
    if got != expected:
        raise HTTPException(status_code=401, detail="invalid telegram ingest token")


@app.on_event("startup")
def _startup():
    _ensure_storage_dir()
    _ensure_db()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/memes/import_from_storage")
def import_from_storage(db: Session = Depends(get_db)):
    _ensure_db()
    storage = _ensure_storage_dir()
    res = import_from_storage_dir(db, storage)
    return {
        "scanned": res.scanned,
        "created": res.created,
        "skipped_existing": res.skipped_existing,
        "skipped_unsupported": res.skipped_unsupported,
    }


@app.post("/memes/clear")
def clear_memes(db: Session = Depends(get_db)):
    _ensure_db()
    deleted_rows = db.query(Meme).delete()
    db.commit()

    storage = _ensure_storage_dir()
    removed_entries = 0
    for item in storage.iterdir():
        if item.is_file() or item.is_symlink():
            item.unlink(missing_ok=True)
            removed_entries += 1
        elif item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
            removed_entries += 1

    return {"deleted_rows": deleted_rows, "removed_storage_entries": removed_entries}


@app.get("/memes")
def list_memes(limit: int = 50, db: Session = Depends(get_db)):
    _ensure_db()
    limit = max(1, min(limit, 200))
    memes = db.scalars(select(Meme).order_by(Meme.id.desc()).limit(limit)).all()
    return [
        {
            "id": m.id,
            "caption": m.caption,
            "source": m.source,
            "filename": m.filename,
            "image_url": f"/memes/{m.id}/image",
        }
        for m in memes
    ]

@app.get("/memes/{meme_id:int}/image")
def meme_image(meme_id: int, db: Session = Depends(get_db)):
    _ensure_db()
    meme = db.get(Meme, meme_id)
    if not meme:
        raise HTTPException(status_code=404, detail="meme not found")

    path = Path(settings.storage_dir) / meme.filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="image file missing")

    return FileResponse(path, media_type=meme.content_type)


@app.post("/memes/upload")
async def upload_meme(
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    _ensure_db()
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="only image/* is allowed")

    data = await file.read()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        ext = None
    return _save_meme_bytes(
        db,
        data=data,
        content_type=file.content_type,
        caption=caption,
        source="upload",
        preferred_ext=ext,
    )


def _create_ai_meme(db: Session, prompt: str | None) -> dict:
    _ensure_db()
    if not settings.allow_generation:
        raise HTTPException(status_code=400, detail="generation disabled")

    prompt = (prompt or "Сгенерируй смешной мем на русском.").strip()
    gen = generate_meme_image(prompt)

    return _save_meme_bytes(
        db,
        data=gen.data,
        content_type=gen.content_type,
        caption=prompt,
        source="ai",
        preferred_ext=".png",
    )


@app.post("/memes/generate")
def generate(prompt: str | None = Form(default=None), db: Session = Depends(get_db)):
    _ensure_db()
    return _create_ai_meme(db, prompt)


@app.get("/memes/random")
def random_meme(
    force_generate: bool = False,
    prompt: str | None = None,
    db: Session = Depends(get_db),
):
    _ensure_db()
    # 1) если есть мемы в базе и не просили генерацию — отдаём случайный
    count = db.scalar(select(func.count()).select_from(Meme)) or 0
    if count > 0 and not force_generate:
        meme = db.scalars(select(Meme).order_by(func.random()).limit(1)).first()
        if not meme:
            raise HTTPException(status_code=500, detail="random select failed")
        return {
            "id": meme.id,
            "caption": meme.caption,
            "source": meme.source,
            "image_url": f"/memes/{meme.id}/image",
        }

    # 2) иначе генерируем (если можно)
    return _create_ai_meme(db, prompt)


@app.get("/memes/{meme_id:int}")
def get_meme(meme_id: int, db: Session = Depends(get_db)):
    # Важно: этот route должен быть ПОСЛЕ /memes/random, иначе /memes/random
    # может попытаться матчиться как /memes/{meme_id} и даст 422.
    _ensure_db()
    meme = db.get(Meme, meme_id)
    if not meme:
        raise HTTPException(status_code=404, detail="meme not found")
    return {
        "id": meme.id,
        "caption": meme.caption,
        "source": meme.source,
        "filename": meme.filename,
        "image_url": f"/memes/{meme.id}/image",
    }


@app.get("/memes/test")
def test():
    return {"message": "Hello, World!"}


@app.post("/telegram/ingest")
async def telegram_ingest(
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    x_telegram_token: str | None = Header(default=None, alias="X-Telegram-Token"),
    db: Session = Depends(get_db),
):
    _ensure_db()
    _require_ingest_token(x_telegram_token)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="only image/* is allowed")
    data = await file.read()
    ext = Path(file.filename or "").suffix.lower() or None
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        ext = None
    return _save_meme_bytes(
        db,
        data=data,
        content_type=file.content_type,
        caption=caption,
        source="telegram",
        preferred_ext=ext,
    )


@app.post("/telegram/fetch_latest")
@app.get("/telegram/fetch_latest")
@app.post("/memes/telegram/fetch_latest")
@app.get("/memes/telegram/fetch_latest")
def telegram_fetch_latest(db: Session = Depends(get_db)):
    _ensure_db()
    updates = _telegram_api_get("getUpdates", limit="100").get("result", [])
    if not isinstance(updates, list):
        raise HTTPException(status_code=502, detail="telegram updates format is invalid")
    message = _extract_latest_telegram_image_message(updates)
    if not message:
        raise HTTPException(status_code=404, detail="no image messages found in telegram updates")

    caption = message.get("caption") or message.get("text")
    content_type = "image/jpeg"
    preferred_ext = ".jpg"

    if message.get("photo"):
        photos = message["photo"]
        file_id = photos[-1]["file_id"]
    else:
        document = message["document"]
        file_id = document["file_id"]
        content_type = document.get("mime_type") or content_type
        preferred_ext = Path(document.get("file_name") or "").suffix.lower() or None

    file_data = _telegram_api_get("getFile", file_id=file_id).get("result", {})
    file_path = file_data.get("file_path")
    if not file_path:
        raise HTTPException(status_code=502, detail="telegram did not return file_path")

    data, downloaded_content_type = _telegram_download_file(file_path)
    final_content_type = content_type or downloaded_content_type
    return _save_meme_bytes(
        db,
        data=data,
        content_type=final_content_type,
        caption=caption,
        source="telegram",
        preferred_ext=preferred_ext,
    )


# Для локальной разработки, если запускать: python -m app.main
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)

import os
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
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

    storage = _ensure_storage_dir()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        # если расширение странное — всё равно сохраним, но как .png-совместимое имя
        ext = ".img"

    filename = f"{uuid.uuid4().hex}{ext}"
    dest = storage / filename

    data = await file.read()
    dest.write_bytes(data)

    meme = Meme(
        caption=caption,
        filename=filename,
        content_type=file.content_type,
        source="upload",
    )
    db.add(meme)
    db.commit()
    db.refresh(meme)

    return {
        "id": meme.id,
        "caption": meme.caption,
        "source": meme.source,
        "image_url": f"/memes/{meme.id}/image",
    }


def _create_ai_meme(db: Session, prompt: str | None) -> dict:
    _ensure_db()
    if not settings.allow_generation:
        raise HTTPException(status_code=400, detail="generation disabled")

    prompt = (prompt or "Сгенерируй смешной мем на русском.").strip()
    gen = generate_meme_image(prompt)

    storage = _ensure_storage_dir()
    filename = f"{uuid.uuid4().hex}.png"
    (storage / filename).write_bytes(gen.data)

    meme = Meme(
        caption=prompt,
        filename=filename,
        content_type=gen.content_type,
        source="ai",
    )
    db.add(meme)
    db.commit()
    db.refresh(meme)

    return {
        "id": meme.id,
        "caption": meme.caption,
        "source": meme.source,
        "image_url": f"/memes/{meme.id}/image",
    }


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


# Для локальной разработки, если запускать: python -m app.main
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)

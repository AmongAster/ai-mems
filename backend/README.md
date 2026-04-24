# Backend (FastAPI) — random meme API

## Что умеет

- `POST /memes/upload` — загрузить картинку и сохранить в базу
- `GET /memes/random` — получить случайный мем из базы, либо сгенерировать новый
- `POST /memes/generate` — принудительно сгенерировать новый мем и сохранить
- `GET /memes/{id}/image` — получить файл картинки

Хранилище:
- SQLite база: `backend/memes.db`
- Файлы картинок: `backend/storage/`

## Быстрый старт (Windows / PowerShell)

В папке `backend`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Проверка:
- `GET http://localhost:8000/health`

## Запуск через Docker Compose

В корне проекта (`ai-mems`):

```powershell
docker compose up --build
```

Проверка:
- `GET http://localhost:8001/health`

По умолчанию в `docker-compose.yml` включён bind-mount:
- локальный `backend/memes.db` монтируется в контейнер как `/data/memes.db`
- локальная папка `backend/storage/` монтируется в контейнер как `/data/storage`

То есть база и картинки в Docker будут ровно те же, что и локально.

## Примеры запросов

### Загрузить мем

```powershell
curl -F "file=@C:\path\to\meme.png" -F "caption=мой мем" http://localhost:8000/memes/upload
```

### Получить рандомный мем

```powershell
curl "http://localhost:8000/memes/random"
```

Ответ будет JSON с `image_url`. Картинку потом получить так:

```powershell
curl -o meme.png "http://localhost:8000<image_url>"
```

### Сгенерировать мем

```powershell
curl -X POST -F "prompt=Сделай мем про дедлайны и кофе" http://localhost:8000/memes/generate
```

## Про AI-генерацию

По умолчанию включён простой локальный генератор (`AI_PROVIDER=local_text`) — он делает PNG с текстом (чтобы всё работало без ключей и внешних сервисов).

Если хочешь OpenAI-генерацию:

1) Поставь пакет:

```powershell
pip install openai
```

2) В `.env`:
- `AI_PROVIDER=openai_images`
- `OPENAI_API_KEY=...`

Если нужно — подключу Stable Diffusion (локально или через API) вместо OpenAI.

## Импорт картинок, которые уже лежат в storage/

Если ты вручную положил файлы в папку `storage/`, их можно “зарегистрировать” в SQLite.

### Консольная команда (локально)

В папке `backend`:

```powershell
py -m app.import_storage
```

Если storage в другом месте:

```powershell
py -m app.import_storage --storage-dir "C:\path\to\storage"
```

### Эндпоинт

```powershell
curl -X POST http://localhost:8001/memes/import_from_storage
```

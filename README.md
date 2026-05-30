# Snap & Shop

Monorepo hackathon: photo → Gemini Vision → Shopify UCP → merchant cart (`continue_url`).

## Structure

```
├── backend/     # FastAPI — POST /scan, GET /health, GET /cart/current
├── web/         # Phase 1 — webcam test UI
└── ios/         # Phase 2+ — SwiftUI Login + Cart (see ios/README.md)
```

See [HACKATHON_PLAN.md](./HACKATHON_PLAN.md) for the full plan.

## Quick start (backend)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # set GEMINI_API_KEY when ready
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/scan -F "file=@shirt.jpg"
```

With `USE_MOCK_UCP=true` (default in `.env.example`), `/scan` returns fake product + `continue_url` without UCP/Gemini keys.

## Web test UI (Phase 1)

Serve `web/` statically while the API runs, e.g.:

```bash
cd web && python3 -m http.server 3000
```

Open http://localhost:3000 — capture from webcam → calls `POST /scan`.

## iOS (Phase 2)

Copy the Meta CameraAccess sample into `ios/CameraAccess/` or use the stub views in `ios/CameraAccess/Views/`. Set `APIConfig.baseURL` to `http://<your-mac-ip>:8000`.

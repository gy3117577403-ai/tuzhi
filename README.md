# Connector CAD Asset System

MVP for connector CAD generation, export, source registry, and audit review. The frontend is a Vite + React SmartCAD-style UI. The backend is FastAPI + CadQuery and generates real STEP, STL, DXF, and JSON artifacts.

## Current Features

- Text, drawing, and photo/scan entry points in the frontend.
- Parametric rectangular connector MVP generation with CadQuery.
- Downloadable `model.step`, `model.stl`, `drawing.dxf`, `params.json`, and `source_manifest.json`.
- Three.js STL preview in the browser.
- Parameter confirmation flow: `needs_confirmation -> confirm-params -> completed`.
- Official/third-party CAD source resolver with parametric fallback.
- CAD source registry with review states: `draft`, `pending_review`, `approved`, `rejected`, `deprecated`.
- Registry file cache, SHA256 tracking, cache integrity checks, audit history, and audit report export.

## MVP Limits

- This is not full connector recognition from drawings or photos.
- Parametric output is an engineering approximation, not an official manufacturer CAD model.
- Official CAD lookup uses a local reviewed registry and manual entries, not a web crawler.
- Registry storage is local JSON with MVP file locks, not a production database.
- Audit signing uses `AUDIT_SIGNING_SECRET`; configure it before production use.

## Backend Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Backend environment:

```powershell
copy backend\.env.example backend\.env
```

Edit `backend/.env` locally:

```env
CONNECTOR_CAD_API_KEY=your-local-api-key
AUDIT_SIGNING_SECRET=change-me-in-production
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
```

## Frontend Setup

```powershell
npm install
npm run dev
```

Frontend environment:

```powershell
copy .env.example .env
```

```env
VITE_API_BASE_URL=http://localhost:8000
```

## Acceptance Flow

1. Start backend on `http://localhost:8000`.
2. Start frontend with `npm run dev`.
3. Open the Vite URL.
4. Generate a connector from text, for example `unknown connector 2 pin`.
5. Confirm parameters if the job returns `needs_confirmation`.
6. Download STEP, STL, DXF, params JSON, and source manifest JSON.
7. Open `CAD 来源库` to create a registry item, approve it, refresh cache, check cache integrity, verify audit signatures, and export an audit report.

## Validation Commands

```powershell
npm run build
cd backend
.\.venv\Scripts\activate
python -m py_compile main.py services/*.py
```

## Files That Must Not Be Committed

Do not commit local secrets or generated artifacts:

- `.env`, `.env.*`, `backend/.env`, `backend/.env.*`
- `node_modules/`, `dist/`
- `backend/.venv/`
- `backend/outputs/`, `backend/generated/`
- `backend/data/cad_registry.json`
- `backend/data/cad_registry_history.json`
- `backend/data/registry_cache/`
- `backend/data/registry_exports/`
- `*.log`

Commit only templates such as `.env.example`, `backend/.env.example`, `backend/data/cad_registry.example.json`, and `backend/data/cad_registry_history.example.json`.

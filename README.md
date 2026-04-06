# Deterministic Linguistic Steganography (React + Python)

This is a one-shot full-stack implementation of deterministic adjective-adverb steganography:

- **Sender / Server**: message -> base-3 trits -> repeated stream -> hash-driven linguistic embedding
- **Receiver / Client**: parse stego text -> recover trits -> majority vote -> reconstruct message

## Architecture

- `backend/`
  - `app/stego.py`: deterministic crypto-linguistic engine
  - `app/main.py`: FastAPI REST + websocket transport
- `frontend/`
  - Vite + React UI for encoding/decoding, capacity estimate, and run metrics

## Features Implemented

- SHA256 mapping: `SHA256(KEY + adv + adj + position) % 3`
- Base-3 alphabet conversion (`a-z` only, 3 trits per char)
- Adjective slot extraction with optional restricted adverb list
- Forward-pass contextual verification for candidate replacements
- Silent-drop handling (remove invalid adjective/adverb pair and retry target trit at next slot)
- Decoder with expected message length and repetition majority vote
- REST endpoints: `/encode`, `/decode`, `/health`
- WebSocket endpoint: `/ws/stego`

## Run Backend

```powershell
cd C:\Users\Sesh\OneDrive\Desktop\aditi_crypt\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -c "import nltk; nltk.download('wordnet')"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If spaCy model is not installed, backend runs in fallback POS mode.

## Run Frontend

```powershell
cd C:\Users\Sesh\OneDrive\Desktop\aditi_crypt\frontend
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173).

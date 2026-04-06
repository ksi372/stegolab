from __future__ import annotations

import json
from typing import Dict, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.stego import (
    NLPProvider,
    analyze_text,
    decode_message,
    encode_message,
)

app = FastAPI(title="Deterministic Linguistic Stego API", version="2.0.0")
nlp = NLPProvider()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request / Response models ───────────────────────────────────────────────

class EncodeRequest(BaseModel):
    cover_text: str = Field(min_length=1)
    message: str = Field(min_length=1)
    key: str = Field(min_length=1)
    repeat: int = Field(default=1, ge=1, le=11)


class DecodeRequest(BaseModel):
    stego_text: str = Field(min_length=1)
    key: str = Field(min_length=1)
    message_length: int = Field(ge=1, le=1024)
    repeat: int = Field(default=1, ge=1, le=11)


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1)


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "nlp_mode": nlp.mode,
        "wordnet": str(nlp._wordnet_available),
    }


@app.post("/encode")
def encode(payload: EncodeRequest) -> Dict[str, object]:
    repeated_message = payload.message * payload.repeat
    result = encode_message(payload.cover_text, repeated_message, payload.key, nlp)
    result["repeat"] = payload.repeat
    result["message_original"] = payload.message
    result["effective_message_length"] = len(result["message_sanitized"]) // payload.repeat
    return result


@app.post("/decode")
def decode(payload: DecodeRequest) -> Dict[str, object]:
    per_pass = payload.message_length
    full_length = per_pass * payload.repeat

    # Decode the entire repeated sequence in one pass
    full_result = decode_message(
        payload.stego_text, payload.key, full_length, nlp
    )
    full_text: str = full_result["decoded_message"]

    # Split into individual repetition passes
    pass_messages: List[str] = []
    for r in range(payload.repeat):
        chunk = full_text[r * per_pass: (r + 1) * per_pass]
        pass_messages.append(chunk)

    # Character-level majority vote across passes
    votes: Dict[int, Dict[str, int]] = {}
    for pass_msg in pass_messages:
        for i, ch in enumerate(pass_msg):
            bucket = votes.setdefault(i, {})
            bucket[ch] = bucket.get(ch, 0) + 1

    merged: List[str] = []
    for i in range(per_pass):
        bucket = votes.get(i, {})
        if not bucket:
            break
        winner = max(bucket.items(), key=lambda x: x[1])[0]
        merged.append(winner)

    return {
        "decoded_message": "".join(merged),
        "pass_messages": pass_messages,
        "repeat": payload.repeat,
        "trits_collected": full_result["trits_collected"],
        "slots_seen": full_result["slots_seen"],
    }


@app.post("/analyze")
def analyze(payload: AnalyzeRequest) -> Dict[str, object]:
    result = analyze_text(payload.text, nlp)
    return result


# ─── WebSocket (real-time stego channel) ─────────────────────────────────────

@app.websocket("/ws/stego")
async def stego_socket(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            action = msg.get("action")

            if action == "encode":
                payload = EncodeRequest(**msg["payload"])
                response = encode(payload)
                response["action"] = "encode_result"
                await ws.send_text(json.dumps(response, default=str))

            elif action == "decode":
                payload = DecodeRequest(**msg["payload"])
                response = decode(payload)
                response["action"] = "decode_result"
                await ws.send_text(json.dumps(response, default=str))

            elif action == "analyze":
                payload = AnalyzeRequest(**msg["payload"])
                response = analyze(payload)
                response["action"] = "analyze_result"
                await ws.send_text(json.dumps(response, default=str))

            else:
                await ws.send_text(
                    json.dumps({"action": "error", "message": "Unknown action"})
                )
    except WebSocketDisconnect:
        return

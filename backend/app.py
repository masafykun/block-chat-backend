"""block-chat: FastAPI バックエンド。

フロント(フォークした scratch-gui)の AIチャットパネルから叩かれる。
起動: OPENAI_API_KEY=... uvicorn app:app --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import generate

app = FastAPI(title="block-chat backend")

# 開発中は全許可。公開時は検証VPSのドメインに絞る。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/chat")
def chat(req: ChatRequest):
    """会話を受け取り、返事＋注入用ブロックを返す。

    フロントは戻り値の blocks / variables / broadcasts を使って
    vm.shareBlocksToTarget() でライブ注入する。
    """
    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    return generate(messages)

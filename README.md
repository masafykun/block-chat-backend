# block-chat — backend

block-chat は、日本語で話しかけると Scratch のブロックに変換し、フォークした
Scratch エディタへ**ライブ注入**する子ども向けプログラミング学習ツールです。

このリポジトリは **バックエンド**（自然言語の解釈とブロック生成）です。
フォークしたエディタ側（AIチャットパネル）は別リポジトリ **block-chat-gui** にあります。

## パイプライン

```
日本語  →  OpenAI (function calling)  →  IR  →  コンパイラ  →  sb3ブロック  →  注入(gui)
```

## 構成

| パス | 役割 |
|---|---|
| `docs/ir-spec.md` | 中間表現(IR)の仕様書 |
| `docs/openai-function-schema.json` | OpenAI function calling のツール定義 |
| `backend/compiler.py` | IR → sb3ブロックJSON コンパイラ（構造バリデータ付き） |
| `backend/agent.py` | OpenAIエージェント：日本語 → IR |
| `backend/app.py` | FastAPIサーバー（`/api/chat`） |
| `backend/chat_cli.py` | フロント無しで試すCLI |
| `backend/test_compiler.py` | コンパイラの検証 |

## 起動

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env          # .env に OPENAI_API_KEY を設定
./venv/bin/uvicorn app:app --host 127.0.0.1 --port 8787
```

`.env` は `.gitignore` 済み。APIキーは絶対にコミットしないこと。

## ライセンス

AGPL-3.0（`LICENSE` 参照）。改造して配布する場合は全ソースの公開が必要です。

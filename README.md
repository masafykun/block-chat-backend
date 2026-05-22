# 🧩 block-chat — backend

> 日本語で話しかけると、Scratch のブロックに変わる。

block-chat は、子どもが日本語で「こうしたい」と話すと、それを Scratch の
ブロックに変換し、エディタへ**ライブ注入**する学習ツールです。
このリポジトリはその**バックエンド**——自然言語の解釈とブロック生成を担います。

![Python](https://img.shields.io/badge/Python-3.10+-3776ab.svg?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688.svg?style=flat-square)
![OpenAI](https://img.shields.io/badge/OpenAI-gpt--5.5-412991.svg?style=flat-square)
![License](https://img.shields.io/badge/License-AGPL%20v3-blue.svg?style=flat-square)

---

## 🧱 2つのリポジトリ

block-chat は2つのリポジトリで構成されます。

| リポジトリ | 役割 |
|---|---|
| **block-chat-backend**（このリポジトリ） | 自然言語の解釈・ブロック生成（IRコンパイラ＋AIエージェント） |
| [**block-chat-gui**](https://github.com/masafykun/block-chat-gui) | フォークした Scratch エディタ＋AIチャットパネル |

🔗 **エディタ側はこちら → [block-chat-gui](https://github.com/masafykun/block-chat-gui)**

---

## 🧠 しくみ

ユーザーの日本語を、確定的に変換できる中間表現（IR）を経由してブロックへ落とします。

```
日本語  →  OpenAI (function calling)  →  IR  →  コンパイラ  →  sb3ブロック  →  注入(gui)
         └──────── agent.py ────────┘        └─ compiler.py ─┘
```

- **IR（中間表現）** — LLMが出しやすく、確定的にブロックへ変換でき、人が読めるAST
- LLMには IR の生成だけを任せ、ブロックの組み立ては確定的なコンパイラが担当する

---

## ✨ 特徴

- **自然言語 → ブロック** — 子どもの言葉を Scratch のスクリプトに変換
- **IR を挟む3層設計** — 「日本語 → IR → ブロック」。LLMの不安定さをIRで吸収
- **構造バリデータ** — 壊れたブロックは注入前に検出して弾く
- **曖昧な依頼は聞き返す** — 作るものが定まらない時はブロックを捏造せず質問する
- **最新モデル** — 解釈に OpenAI gpt-5.5 を使用

---

## 🛠️ 技術スタック

| カテゴリ | 技術 |
|---|---|
| 言語 | Python |
| AIモデル | OpenAI gpt-5.5（function calling） |
| Webフレームワーク | FastAPI / Uvicorn |
| 出力形式 | Scratch 3.0 プロジェクト形式（sb3 ブロックJSON） |

---

## 📁 ディレクトリ構成

```
block-chat-backend/
├── docs/
│   ├── ir-spec.md                  IR（中間表現）の仕様書
│   └── openai-function-schema.json OpenAI function calling スキーマ
└── backend/
    ├── compiler.py                 IR → sb3ブロック コンパイラ（バリデータ付き）
    ├── agent.py                    OpenAIエージェント（日本語 → IR）
    ├── app.py                      FastAPIサーバー（/api/chat）
    ├── chat_cli.py                 フロント無しで試すCLI
    ├── test_compiler.py            コンパイラの検証
    └── requirements.txt
```

---

## 🚀 セットアップ

```bash
cd backend
python3 -m venv venv                          # 仮想環境を作成
./venv/bin/pip install -r requirements.txt    # 依存パッケージを導入
cp .env.example .env                          # .env に OPENAI_API_KEY を設定
./venv/bin/uvicorn app:app --host 127.0.0.1 --port 8787   # サーバー起動
```

CLI で単体検証（`out_chat.sb3` が出力され、Scratch で開ける）:

```bash
cd backend
./venv/bin/python chat_cli.py "ねこを旗で10歩ずつずっと動かして"
```

---

## 🔑 環境変数

`backend/.env` に設定する（`.gitignore` 済み。APIキーは絶対にコミットしない）。

| 変数名 | 説明 | 必須 |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI APIキー | ✅ |
| `OPENAI_MODEL` | 使うモデル（未指定なら `gpt-5.5`） | — |

---

## ライセンス

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg?style=flat-square)](https://www.gnu.org/licenses/agpl-3.0)

このプロジェクトは **GNU AGPL-3.0** のもとで公開しています。
改造して配布・ネットワーク提供する場合は、全ソースコードの公開が必要です。

© 2026 masafykun (https://github.com/masafykun)

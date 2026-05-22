"""block-chat: 日本語の依頼 -> OpenAI(function calling) -> IR -> ブロック の中核。

OpenAI に openai-function-schema.json のツールを渡し、ユーザーの依頼を IR に変換させる。
返ってきた IR を compiler.py でブロック化して返す。

APIキーはコードに書かない。環境変数 OPENAI_API_KEY から OpenAI SDK が自動で読む。
"""
import json, os
from dotenv import load_dotenv
from compiler import Compiler

_HERE = os.path.dirname(os.path.abspath(__file__))

# backend/.env から OPENAI_API_KEY 等を読み込む（キーをコードに書かないため）。
load_dotenv(os.path.join(_HERE, ".env"))

# 既定は最新フラッグシップ gpt-5.5。コスト優先なら環境変数 OPENAI_MODEL で
# gpt-5.4-mini 等に切り替え可能。
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.5")
SCHEMA_PATH = os.path.join(_HERE, "..", "docs", "openai-function-schema.json")


def _load_tool():
    """function calling 用ツール定義を読み込む(_comment は除去)。"""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_comment", None)
    return data


TOOL = _load_tool()

SYSTEM_PROMPT = """あなたは「block-chat」という、子ども向けプログラミング学習ツールのアシスタントです。
ユーザー（主に子ども）が日本語で「こんなプログラムを作りたい」と話しかけてきます。
あなたの仕事は、その依頼を Scratch のブロックに変換することです。

# いつ関数を呼ぶか
- 依頼が具体的で、作るものが明確なら、add_to_project 関数を呼んでブロックを作ってください。
- 依頼が曖昧で何を作るか決められないときは、関数を呼ばず、日本語でやさしく聞き返してください。
  例:「ねこをどんなふうに動かしたい？ ずっと？ それとも1回だけ？」

# 返事のしかた
- 子どもにわかる、短くてやさしい日本語で。励ます感じで。
- ブロックを作ったときは summary フィールドに「何を作ったか」を1〜2文の日本語で必ず書く。
  これがそのまま子どもへの説明になります。

# IR（add_to_project の引数）の作り方
- scripts は「ハット(when=いつ動くか) + body(順番に積む文の列)」の集まり。
- ループ(repeat/forever)や もし(if/if_else)は body の中にさらに文を入れる（ネスト）。
- 入力値は、数値や文字列をそのまま書くか、式オブジェクト {"expr": ...} を入れる。
  例: スコアを1増やす → set_var の value に
      {"expr":"+","a":{"expr":"var","name":"スコア"},"b":1}
- 変数やメッセージは使った時点で自動的に作られる。宣言は不要。
- スキーマの do / expr / event の一覧に無いブロックは使えない。
  無い機能を頼まれたら、近いブロックで実現するか、できないと正直に伝える。
- 既存ブロックの編集・削除はできない。新しく追加するだけ。

# 安全
- 不適切な内容や、Scratchで作れないもの（ファイル操作・ネット通信など）はやさしく断る。
"""


def generate(messages):
    """会話履歴から、返事とブロックを生成する。

    messages: [{"role": "user"|"assistant", "content": str}, ...]
    戻り値: {
        reply: 子どもへの返事(str),
        ir: 生成されたIR(dict) または None,
        blocks: sb3ブロックJSON(dict) または None,
        variables: {名前: id}, broadcasts: {名前: id},
        summary: str, errors: [str],
    }
    """
    from openai import OpenAI  # APIキー不要な場面でも import できるよう遅延読み込み
    client = OpenAI()

    full = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    # temperature は指定しない（GPT-5系は既定値以外を受け付けない場合があるため）。
    # function calling + スキーマ制約で出力は十分安定する。
    resp = client.chat.completions.create(
        model=MODEL,
        messages=full,
        tools=[TOOL],
        tool_choice="auto",
    )
    msg = resp.choices[0].message

    result = {"reply": msg.content or "", "ir": None, "blocks": None,
              "variables": {}, "broadcasts": {}, "summary": "", "errors": []}

    if not msg.tool_calls:
        # 関数を呼ばなかった = 曖昧なので聞き返している
        return result

    call = msg.tool_calls[0]
    try:
        ir = json.loads(call.function.arguments)
    except json.JSONDecodeError as e:
        result["errors"] = [f"IRのJSON解析に失敗: {e}"]
        return result

    # IR をブロックへコンパイル（確定的処理・バリデータ付き）
    comp = Compiler().compile(ir)
    result.update({
        "ir": ir,
        "blocks": comp["blocks"],
        "variables": comp["variables"],
        "broadcasts": comp["broadcasts"],
        "summary": comp["summary"],
        "errors": comp["errors"],
    })
    if not result["reply"]:
        result["reply"] = comp["summary"] or "ブロックを追加したよ！"
    # NOTE: comp["errors"] があるときは v1.1 でエラーを LLM に戻して再生成させる予定。
    return result

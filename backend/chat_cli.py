"""block-chat: フロント無しで「日本語 -> ブロック」を試す CLI。

使い方:
  export OPENAI_API_KEY=...        # キーは環境変数に。コードには書かない
  python3 chat_cli.py "ねこを旗で10歩ずつずっと動かして"

依頼ごとに out_chat.sb3 を書き出すので、Scratch で開いて確認できる。
"""
import json, os, sys
from agent import generate
from compiler import build_sb3

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out_chat.sb3")


def main():
    prompt = " ".join(sys.argv[1:]).strip() or input("依頼: ").strip()
    if not prompt:
        print("依頼が空です。")
        return

    result = generate([{"role": "user", "content": prompt}])

    print("\n返事:", result["reply"])

    if result["errors"]:
        print("エラー:", result["errors"])

    if result["ir"] is None:
        print("(ブロックは作られませんでした — 聞き返しの返事です)")
        return

    print("\nIR:")
    print(json.dumps(result["ir"], ensure_ascii=False, indent=2))

    build_sb3(result["ir"], OUT)
    print(f"\n変数: {list(result['variables'])}  メッセージ: {list(result['broadcasts'])}")
    print(f"-> {OUT} （Scratch で開いて確認）")


if __name__ == "__main__":
    main()

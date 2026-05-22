"""IR -> sb3 コンパイラの検証。
IR仕様書の例を含む数パターンをコンパイルし、構造チェック後に .sb3 を書き出す。
出力された .sb3 を Scratch で開けば実機確認できる。
"""
import os
from compiler import build_sb3

OUT = os.path.dirname(os.path.abspath(__file__))

# --- 例1: ir-spec.md の「端で跳ね返る」 -------------------------------
ex_bounce = {
    "ir_version": 1,
    "summary": "旗が押されたら、ずっと10歩進んで端で跳ね返ります",
    "target": None,
    "scripts": [{
        "when": {"event": "flag"},
        "body": [
            {"do": "forever", "body": [
                {"do": "move", "steps": 10},
                {"do": "if",
                 "condition": {"expr": "touching", "what": "edge"},
                 "body": [{"do": "turn", "direction": "right", "degrees": 180}]},
            ]},
        ],
    }],
}

# --- 例2: 変数・式・キーイベント・broadcast ---------------------------
ex_counter = {
    "ir_version": 1,
    "summary": "スペースキーでスコアを1ずつ増やし、10になったら知らせます",
    "target": None,
    "scripts": [
        {"when": {"event": "flag"},
         "body": [{"do": "set_var", "name": "スコア", "value": 0}]},
        {"when": {"event": "key", "key": "space"},
         "body": [
             {"do": "change_var", "name": "スコア", "by": 1},
             {"do": "say", "message": {"expr": "join",
                                       "a": "スコア: ",
                                       "b": {"expr": "var", "name": "スコア"}},
              "secs": 1},
             {"do": "if_else",
              "condition": {"expr": ">", "a": {"expr": "var", "name": "スコア"}, "b": 9},
              "body": [{"do": "broadcast", "message": "クリア"}],
              "else": [{"do": "wait", "secs": 0.1}]},
         ]},
        {"when": {"event": "broadcast_received", "message": "クリア"},
         "body": [{"do": "say", "message": "10てんだ！🎉", "secs": 3}]},
    ],
}

# --- 例3: ネストした式・繰り返し・乱数 --------------------------------
ex_random = {
    "ir_version": 1,
    "summary": "旗が押されたら5回、ランダムな場所へ動いて少し待ちます",
    "target": None,
    "scripts": [{
        "when": {"event": "flag"},
        "body": [
            {"do": "repeat", "times": 5, "body": [
                {"do": "go_to_xy",
                 "x": {"expr": "random", "from": -200, "to": 200},
                 "y": {"expr": "random", "from": -150, "to": 150}},
                {"do": "wait", "secs": {"expr": "random", "from": 0.2, "to": 1}},
            ]},
            {"do": "say", "message": "おわり", "secs": 2},
        ],
    }],
}

CASES = [("bounce", ex_bounce), ("counter", ex_counter), ("random", ex_random)]

if __name__ == "__main__":
    all_ok = True
    for name, ir in CASES:
        path = os.path.join(OUT, f"out_{name}.sb3")
        result = build_sb3(ir, path)
        nblocks = len(result["blocks"])
        status = "OK" if result["ok"] else "NG"
        print(f"[{status}] {name:8s} ブロック{nblocks:3d}  変数{list(result['variables'])}  "
              f"メッセージ{list(result['broadcasts'])}")
        if result["errors"]:
            all_ok = False
            for e in result["errors"]:
                print("        -", e)
        print(f"         -> {path}")
    print("総合:", "全ケース構造チェック通過" if all_ok else "エラーあり")

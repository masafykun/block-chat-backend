# block-chat IR 仕様書 (v1)

`block-chat` の中間表現（Intermediate Representation）の仕様。

```
ユーザーの日本語  →  OpenAI(function calling)  →  IR  →  sb3ブロックJSON  →  vm.shareBlocksToTarget()
                                            └ 本書が定義 ┘   └ コンパイラ ┘      └ ライブ注入 ┘
```

IR は「LLM が出しやすく」「確定的にブロックへ変換でき」「人が読める」ことを同時に満たす AST（抽象構文木）。

---

## 1. 階層

```
トップ        { ir_version, summary, target, scripts: [...] }
 └ script     { when: <hat>, body: [<statement>, ...] }
     └ statement  1つのスタックブロック。loop/if は body を内包
         └ expression  入力値。リテラル or ネストした関数/真偽ブロック
```

---

## 2. トップレベル

| フィールド | 型 | 説明 |
|---|---|---|
| `ir_version` | number | 仕様バージョン。現在 `1` |
| `summary` | string | 学習者に見せる日本語の説明文（「こう作るよ」） |
| `target` | string \| null | 注入先スプライト名。`null` = 現在選択中のスプライト |
| `scripts` | script[] | 追加するスクリプト群 |

---

## 3. ハット `when`

スクリプトの開始ブロック。`event` で種別を判別。

| IR | Scratchブロック | sb3 opcode |
|---|---|---|
| `{"event":"flag"}` | 緑の旗が押されたとき | `event_whenflagclicked` |
| `{"event":"key","key":"space"}` | キーが押されたとき | `event_whenkeypressed` |
| `{"event":"sprite_clicked"}` | スプライトが押されたとき | `event_whenthisspriteclicked` |
| `{"event":"broadcast_received","message":"start"}` | メッセージを受け取ったとき | `event_whenbroadcastreceived` |
| `{"event":"clone_start"}` | クローンされたとき | `control_start_as_clone` |

`key` 候補: `space` / `up arrow` / `down arrow` / `left arrow` / `right arrow` / `a`〜`z` / `0`〜`9` / `any`

---

## 4. 文 `do` — スタックブロック

すべて `{ "do": "<名前>", ...パラメータ }`。

### 動き
| do | パラメータ | opcode |
|---|---|---|
| `move` | `steps` | `motion_movesteps` |
| `turn` | `direction`(`right`\|`left`), `degrees` | `motion_turnright` / `motion_turnleft` |
| `go_to_xy` | `x`, `y` | `motion_gotoxy` |
| `glide_to_xy` | `secs`, `x`, `y` | `motion_glidesecstoxy` |
| `point_in_direction` | `degrees` | `motion_pointindirection` |
| `change_x` | `by` | `motion_changexby` |
| `set_x` | `to` | `motion_setx` |
| `change_y` | `by` | `motion_changeyby` |
| `set_y` | `to` | `motion_sety` |
| `if_on_edge_bounce` | — | `motion_ifonedgebounce` |

### 見た目
| do | パラメータ | opcode |
|---|---|---|
| `say` | `message`, `secs`(任意) | `looks_say` / `looks_sayforsecs` |
| `think` | `message`, `secs`(任意) | `looks_think` / `looks_thinkforsecs` |
| `switch_costume` | `costume` | `looks_switchcostumeto` |
| `next_costume` | — | `looks_nextcostume` |
| `show` / `hide` | — | `looks_show` / `looks_hide` |
| `change_size` | `by` | `looks_changesizeby` |
| `set_size` | `to` | `looks_setsizeto` |
| `set_effect` | `effect`, `to` | `looks_seteffectto` |
| `change_effect` | `effect`, `by` | `looks_changeeffectby` |

`effect` 候補: `color` / `fisheye` / `whirl` / `pixelate` / `mosaic` / `brightness` / `ghost`

### 音
| do | パラメータ | opcode |
|---|---|---|
| `play_sound` | `sound`, `wait`(任意, 既定 false) | `sound_play` / `sound_playuntildone` |
| `stop_all_sounds` | — | `sound_stopallsounds` |

### 制御
| do | パラメータ | opcode |
|---|---|---|
| `wait` | `secs` | `control_wait` |
| `repeat` | `times`, `body` | `control_repeat` |
| `forever` | `body` | `control_forever` |
| `if` | `condition`, `body` | `control_if` |
| `if_else` | `condition`, `body`, `else` | `control_if_else` |
| `wait_until` | `condition` | `control_wait_until` |
| `repeat_until` | `condition`, `body` | `control_repeat_until` |
| `stop` | `what`(`all`\|`this_script`\|`other_scripts`) | `control_stop` |
| `create_clone` | `of`(`myself` または スプライト名) | `control_create_clone_of` |
| `delete_clone` | — | `control_delete_this_clone` |

### イベント
| do | パラメータ | opcode |
|---|---|---|
| `broadcast` | `message`, `wait`(任意, 既定 false) | `event_broadcast` / `event_broadcastandwait` |

### 変数
| do | パラメータ | opcode |
|---|---|---|
| `set_var` | `name`, `value` | `data_setvariableto` |
| `change_var` | `name`, `by` | `data_changevariableby` |

---

## 5. 式 `expr` — 入力値

入力スロットには **リテラル**（数値・文字列・真偽）か **式オブジェクト** `{ "expr": ... }` のどちらも置ける。

### 値を返す式（reporter）
| expr | パラメータ | opcode |
|---|---|---|
| `var` | `name` | 変数プリミティブ `[12,name,id]` |
| `random` | `from`, `to` | `operator_random` |
| `+` `-` `*` `/` | `a`, `b` | `operator_add`/`subtract`/`multiply`/`divide` |
| `join` | `a`, `b` | `operator_join` |
| `x_position` / `y_position` / `direction` / `size` | — | `motion_xposition` 等 |
| `mouse_x` / `mouse_y` / `timer` / `answer` | — | `sensing_mousex` 等 |

### 真偽を返す式（boolean）
| expr | パラメータ | opcode |
|---|---|---|
| `=` `<` `>` | `a`, `b` | `operator_equals`/`lt`/`gt` |
| `and` / `or` | `a`, `b` | `operator_and` / `operator_or` |
| `not` | `a` | `operator_not` |
| `touching` | `what`(`edge`\|`mouse` または スプライト名) | `sensing_touchingobject` |
| `key_pressed` | `key` | `sensing_keypressed` |
| `mouse_down` | — | `sensing_mousedown` |

`condition`（if / wait_until / repeat_until）には **真偽を返す式**のみ置ける。

---

## 6. 例

### 6.1 端で跳ね返る
```json
{
  "ir_version": 1,
  "summary": "旗が押されたら、ずっと10歩進んで端で跳ね返ります",
  "target": null,
  "scripts": [{
    "when": { "event": "flag" },
    "body": [
      { "do": "forever", "body": [
        { "do": "move", "steps": 10 },
        { "do": "if",
          "condition": { "expr": "touching", "what": "edge" },
          "body": [ { "do": "turn", "direction": "right", "degrees": 180 } ] }
      ]}
    ]
  }]
}
```

### 6.2 リテラルと式の混在（score を1増やす）
```json
{ "do": "set_var", "name": "score",
  "value": { "expr": "+", "a": { "expr": "var", "name": "score" }, "b": 1 } }
```

---

## 7. コンパイラの責務

IR → sb3 ブロックJSON への変換時にコンパイラが担う：

1. ブロックID採番、`parent`/`next` のリンク、`body` → サブスタック化
2. シャドウブロック生成（数値シャドウ・メニュー: `sensing_touchingobjectmenu` 等）
3. ネストした式 → reporter入力 `[3, child, shadow]` への展開
4. **未定義の変数・メッセージを自動生成**（変数はステージにグローバル定義）
5. 構造バリデーション（参照切れ・型不整合を検出）→ **不正なら注入せず破棄しエラー返却**
6. トップレベルブロックの座標を決定（ワークスペースの空き領域に配置）

---

## 8. スコープと方針 (v1)

- **追加専用**。既存ブロックの編集・削除は対象外（既存ブロックIDの参照が必要なため v2 以降）
- 曖昧な依頼では LLM は function を呼ばず、文章で聞き返してよい（IRを捏造させない）
- 音楽拡張・ペン拡張などは `do` / `expr` を追加して段階拡張。その際 `ir_version` を上げる
- `summary` と IR の可読性を使い、注入前に「①〜 ②〜」と日本語手順で学習者に提示する

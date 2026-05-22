"""block-chat: IR -> sb3 ブロックJSON コンパイラ。

IR(ir-spec.md / openai-function-schema.json で定義)を受け取り、
Scratch の sb3 ブロック辞書に変換する。確定的処理(LLM不要)。

本番では compile() の出力(blocks)を vm.shareBlocksToTarget() に渡してライブ注入する。
単体検証用に build_sb3() で完全な .sb3 を書き出せる。
"""
import hashlib, json, zipfile, os

# ----------------------------------------------------------------------
# 入力値ヘルパー
# ----------------------------------------------------------------------
def _num(v):  return [1, [4, str(v)]]      # 数値シャドウ
def _txt(v):  return [1, [10, str(v)]]     # 文字列シャドウ

BOOLEAN_EXPRS = {"=", "<", ">", "and", "or", "not",
                 "touching", "key_pressed", "mouse_down"}

# 文 do -> (opcode, 数値/値入力名のマップ)。単純なものはここで処理。
# 複雑なもの(可変opcode・メニュー・body)は compile_statement 内で個別処理。
SIMPLE_STMT = {
    "move":               ("motion_movesteps",      {"steps": "STEPS"}),
    "go_to_xy":            ("motion_gotoxy",         {"x": "X", "y": "Y"}),
    "glide_to_xy":         ("motion_glidesecstoxy",  {"secs": "SECS", "x": "X", "y": "Y"}),
    "point_in_direction":  ("motion_pointindirection", {"degrees": "DIRECTION"}),
    "change_x":            ("motion_changexby",      {"by": "DX"}),
    "set_x":               ("motion_setx",           {"to": "X"}),
    "change_y":            ("motion_changeyby",      {"by": "DY"}),
    "set_y":               ("motion_sety",           {"to": "Y"}),
    "if_on_edge_bounce":   ("motion_ifonedgebounce", {}),
    "next_costume":        ("looks_nextcostume",     {}),
    "show":                ("looks_show",            {}),
    "hide":                ("looks_hide",            {}),
    "change_size":         ("looks_changesizeby",    {"by": "CHANGE"}),
    "set_size":            ("looks_setsizeto",       {"to": "SIZE"}),
    "stop_all_sounds":     ("sound_stopallsounds",   {}),
    "wait":                ("control_wait",          {"secs": "DURATION"}),
    "delete_clone":        ("control_delete_this_clone", {}),
}


class Compiler:
    def __init__(self):
        self.blocks = {}
        self.variables = {}    # 変数名 -> id
        self.broadcasts = {}   # メッセージ名 -> id
        self.errors = []
        self._n = 0

    # -- ID採番 / 自動生成 ---------------------------------------------
    def gen(self, p="b"):
        self._n += 1
        return f"{p}{self._n}"

    def var_id(self, name):
        name = str(name or "へんすう")
        if name not in self.variables:
            self.variables[name] = self.gen("var")
        return self.variables[name]

    def bcast_id(self, name):
        name = str(name or "メッセージ")
        if name not in self.broadcasts:
            self.broadcasts[name] = self.gen("bc")
        return self.broadcasts[name]

    # -- 値 / 式 --------------------------------------------------------
    def compile_value(self, val, parent):
        """通常入力(丸)用。リテラルor式 -> 入力スペック。"""
        if isinstance(val, bool):
            return _txt("true" if val else "false")
        if isinstance(val, (int, float)):
            return _num(val)
        if isinstance(val, str):
            return _txt(val)
        if isinstance(val, dict) and "expr" in val:
            if val["expr"] == "var":                       # 変数はブロックでなくプリミティブ
                vid = self.var_id(val.get("name"))
                return [3, [12, str(val.get("name")), vid], [10, ""]]
            eid = self.compile_expression(val, parent)
            return [3, eid, [10, ""]]
        self.errors.append(f"値として解釈できません: {val!r}")
        return _num(0)

    def compile_condition(self, val, parent):
        """真偽入力(六角形)用。-> [2, id] または None。"""
        if isinstance(val, dict) and "expr" in val:
            eid = self.compile_expression(val, parent)
            return [2, eid]
        self.errors.append(f"条件が式ではありません: {val!r}")
        return None

    def _menu(self, parent, opcode, field, value):
        mid = self.gen("m")
        self.blocks[mid] = {"opcode": opcode, "next": None, "parent": parent,
                            "inputs": {}, "fields": {field: [value, None]},
                            "shadow": True, "topLevel": False}
        return mid

    def compile_expression(self, expr, parent):
        name = expr.get("expr")
        eid = self.gen("e")
        inputs, fields, opcode = {}, {}, None

        if name in ("+", "-", "*", "/"):
            opcode = {"+": "operator_add", "-": "operator_subtract",
                      "*": "operator_multiply", "/": "operator_divide"}[name]
            inputs["NUM1"] = self.compile_value(expr.get("a", 0), eid)
            inputs["NUM2"] = self.compile_value(expr.get("b", 0), eid)
        elif name == "join":
            opcode = "operator_join"
            inputs["STRING1"] = self.compile_value(expr.get("a", ""), eid)
            inputs["STRING2"] = self.compile_value(expr.get("b", ""), eid)
        elif name == "random":
            opcode = "operator_random"
            inputs["FROM"] = self.compile_value(expr.get("from", 1), eid)
            inputs["TO"] = self.compile_value(expr.get("to", 10), eid)
        elif name in ("=", "<", ">"):
            opcode = {"=": "operator_equals", "<": "operator_lt", ">": "operator_gt"}[name]
            inputs["OPERAND1"] = self.compile_value(expr.get("a", 0), eid)
            inputs["OPERAND2"] = self.compile_value(expr.get("b", 0), eid)
        elif name in ("and", "or"):
            opcode = "operator_and" if name == "and" else "operator_or"
            for slot, key in (("OPERAND1", "a"), ("OPERAND2", "b")):
                c = self.compile_condition(expr.get(key), eid)
                if c:
                    inputs[slot] = c
        elif name == "not":
            opcode = "operator_not"
            c = self.compile_condition(expr.get("a"), eid)
            if c:
                inputs["OPERAND"] = c
        elif name == "touching":
            opcode = "sensing_touchingobject"
            what = expr.get("what", "edge")
            val = {"edge": "_edge_", "mouse": "_mouse_"}.get(what, what)
            mid = self._menu(eid, "sensing_touchingobjectmenu", "TOUCHINGOBJECTMENU", val)
            inputs["TOUCHINGOBJECTMENU"] = [1, mid]
        elif name == "key_pressed":
            opcode = "sensing_keypressed"
            mid = self._menu(eid, "sensing_keyoptions", "KEY_OPTION", expr.get("key", "space"))
            inputs["KEY_OPTION"] = [1, mid]
        else:
            simple = {"x_position": "motion_xposition", "y_position": "motion_yposition",
                      "direction": "motion_direction", "size": "looks_size",
                      "mouse_x": "sensing_mousex", "mouse_y": "sensing_mousey",
                      "timer": "sensing_timer", "answer": "sensing_answer",
                      "mouse_down": "sensing_mousedown"}
            opcode = simple.get(name)
            if opcode is None:
                self.errors.append(f"未知の式: {name}")
                opcode = "operator_equals"

        self.blocks[eid] = {"opcode": opcode, "next": None, "parent": parent,
                            "inputs": inputs, "fields": fields,
                            "shadow": False, "topLevel": False}
        return eid

    # -- 文 -------------------------------------------------------------
    def compile_body(self, stmts, parent):
        """文の配列 -> スタック連結。先頭ブロックidを返す。"""
        ids = [self.compile_statement(s) for s in (stmts or [])]
        for i, bid in enumerate(ids):
            self.blocks[bid]["parent"] = parent if i == 0 else ids[i - 1]
            self.blocks[bid]["next"] = ids[i + 1] if i + 1 < len(ids) else None
        return ids[0] if ids else None

    def compile_statement(self, stmt):
        do = stmt.get("do")
        bid = self.gen()
        inputs, fields, opcode, mutation = {}, {}, None, None

        if do in SIMPLE_STMT:
            opcode, vmap = SIMPLE_STMT[do]
            for key, slot in vmap.items():
                inputs[slot] = self.compile_value(stmt.get(key, 0), bid)

        elif do == "turn":
            opcode = "motion_turnleft" if stmt.get("direction") == "left" else "motion_turnright"
            inputs["DEGREES"] = self.compile_value(stmt.get("degrees", 15), bid)

        elif do in ("say", "think"):
            timed = "secs" in stmt
            opcode = f"looks_{do}forsecs" if timed else f"looks_{do}"
            inputs["MESSAGE"] = self.compile_value(stmt.get("message", ""), bid)
            if timed:
                inputs["SECS"] = self.compile_value(stmt.get("secs", 2), bid)

        elif do == "switch_costume":
            opcode = "looks_switchcostumeto"
            mid = self._menu(bid, "looks_costume", "COSTUME", stmt.get("costume", ""))
            inputs["COSTUME"] = [1, mid]

        elif do in ("set_effect", "change_effect"):
            opcode = "looks_seteffectto" if do == "set_effect" else "looks_changeeffectby"
            fields["EFFECT"] = [str(stmt.get("effect", "ghost")).upper(), None]
            slot = "VALUE" if do == "set_effect" else "CHANGE"
            key = "to" if do == "set_effect" else "by"
            inputs[slot] = self.compile_value(stmt.get(key, 0), bid)

        elif do == "play_sound":
            opcode = "sound_playuntildone" if stmt.get("wait") else "sound_play"
            mid = self._menu(bid, "sound_sounds_menu", "SOUND_MENU", stmt.get("sound", ""))
            inputs["SOUND_MENU"] = [1, mid]

        elif do in ("repeat", "repeat_until", "forever", "if", "if_else", "wait_until"):
            opcode = {"repeat": "control_repeat", "repeat_until": "control_repeat_until",
                      "forever": "control_forever", "if": "control_if",
                      "if_else": "control_if_else", "wait_until": "control_wait_until"}[do]
            if do == "repeat":
                inputs["TIMES"] = self.compile_value(stmt.get("times", 10), bid)
            if do in ("if", "if_else", "repeat_until", "wait_until"):
                cond = self.compile_condition(stmt.get("condition"), bid)
                if cond:
                    inputs["CONDITION"] = cond
            if do != "wait_until":
                first = self.compile_body(stmt.get("body"), bid)
                if first:
                    inputs["SUBSTACK"] = [2, first]
            if do == "if_else":
                first2 = self.compile_body(stmt.get("else"), bid)
                if first2:
                    inputs["SUBSTACK2"] = [2, first2]

        elif do == "stop":
            opcode = "control_stop"
            what = stmt.get("what", "all")
            label = {"all": "all", "this_script": "this script",
                     "other_scripts": "other scripts in sprite"}.get(what, "all")
            fields["STOP_OPTION"] = [label, None]
            mutation = {"tagName": "mutation", "children": [],
                        "hasnext": "true" if what == "other_scripts" else "false"}

        elif do == "create_clone":
            opcode = "control_create_clone_of"
            of = stmt.get("what") or stmt.get("of") or "myself"
            val = "_myself_" if of == "myself" else of
            mid = self._menu(bid, "control_create_clone_of_menu", "CLONE_OPTION", val)
            inputs["CLONE_OPTION"] = [1, mid]

        elif do == "broadcast":
            opcode = "event_broadcastandwait" if stmt.get("wait") else "event_broadcast"
            msg = str(stmt.get("message", "メッセージ"))
            inputs["BROADCAST_INPUT"] = [1, [11, msg, self.bcast_id(msg)]]

        elif do in ("set_var", "change_var"):
            opcode = "data_setvariableto" if do == "set_var" else "data_changevariableby"
            name = str(stmt.get("name", "へんすう"))
            fields["VARIABLE"] = [name, self.var_id(name)]
            key = "value" if do == "set_var" else "by"
            inputs["VALUE"] = self.compile_value(stmt.get(key, 0), bid)

        else:
            self.errors.append(f"未知の文: {do}")
            opcode = "control_wait"
            inputs["DURATION"] = _num(0)

        self.blocks[bid] = {"opcode": opcode, "next": None, "parent": None,
                            "inputs": inputs, "fields": fields,
                            "shadow": False, "topLevel": False}
        if mutation:
            self.blocks[bid]["mutation"] = mutation
        return bid

    # -- ハット ---------------------------------------------------------
    def compile_hat(self, hat, x, y):
        event = hat.get("event")
        hid = self.gen("h")
        inputs, fields = {}, {}
        if event == "flag":
            opcode = "event_whenflagclicked"
        elif event == "key":
            opcode = "event_whenkeypressed"
            fields["KEY_OPTION"] = [hat.get("key", "space"), None]
        elif event == "sprite_clicked":
            opcode = "event_whenthisspriteclicked"
        elif event == "broadcast_received":
            opcode = "event_whenbroadcastreceived"
            msg = str(hat.get("message", "メッセージ"))
            fields["BROADCAST_OPTION"] = [msg, self.bcast_id(msg)]
        elif event == "clone_start":
            opcode = "control_start_as_clone"
        else:
            self.errors.append(f"未知のイベント: {event}")
            opcode = "event_whenflagclicked"
        self.blocks[hid] = {"opcode": opcode, "next": None, "parent": None,
                            "inputs": inputs, "fields": fields,
                            "shadow": False, "topLevel": True, "x": x, "y": y}
        return hid

    # -- スクリプト / 全体 ----------------------------------------------
    def compile_script(self, script, x, y):
        hid = self.compile_hat(script.get("when", {}), x, y)
        first = self.compile_body(script.get("body"), hid)
        if first:
            self.blocks[hid]["next"] = first
        return hid

    def compile(self, ir):
        for i, script in enumerate(ir.get("scripts", [])):
            self.compile_script(script, 60, 60 + i * 260)
        self.errors += validate(self.blocks)
        return {
            "summary": ir.get("summary", ""),
            "blocks": self.blocks,
            "variables": self.variables,    # 名前 -> id
            "broadcasts": self.broadcasts,  # 名前 -> id
            "errors": self.errors,
            "ok": not self.errors,
        }


# ----------------------------------------------------------------------
# 構造バリデータ (build_game.py と同方針: 参照切れ検出)
# ----------------------------------------------------------------------
def validate(blocks):
    errs = []
    ids = set(blocks)
    for bid, b in blocks.items():
        for link in ("next", "parent"):
            ref = b.get(link)
            if ref is not None and ref not in ids:
                errs.append(f"{bid}.{link} -> 未定義 '{ref}'")
        for iname, ival in b["inputs"].items():
            for slot in ival[1:]:
                if isinstance(slot, str) and slot not in ids:
                    errs.append(f"{bid}.inputs.{iname} -> 未定義 '{slot}'")
    return errs


# ----------------------------------------------------------------------
# 単体検証用: コンパイル結果を完全な .sb3 にして書き出す
# ----------------------------------------------------------------------
_CAT = ('<svg xmlns="http://www.w3.org/2000/svg" width="60" height="60" viewBox="0 0 60 60">'
        '<ellipse cx="30" cy="40" rx="18" ry="14" fill="#f9a13b"/>'
        '<circle cx="33" cy="22" r="14" fill="#f9a13b"/>'
        '<path d="M24 12 l-3 -9 9 5 z M42 12 l3 -9 -9 5 z" fill="#f9a13b"/>'
        '<circle cx="29" cy="21" r="3" fill="#33260f"/><circle cx="38" cy="21" r="3" fill="#33260f"/>'
        '</svg>')

# ステージ用の無地の背景 (480x360)。スプライトのコスチュームとは別アセットにする。
_BACKDROP = ('<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360" '
             'viewBox="0 0 480 360"><rect width="480" height="360" fill="#ffffff"/></svg>')


def _asset(svg_str):
    b = svg_str.encode("utf-8")
    return hashlib.md5(b).hexdigest(), b


def _costume(md5, name, cx, cy):
    return {"assetId": md5, "name": name, "bitmapResolution": 1,
            "md5ext": md5 + ".svg", "dataFormat": "svg",
            "rotationCenterX": cx, "rotationCenterY": cy}


def build_sb3(ir, path):
    """IR をコンパイルし、ステージ(無地背景)＋スプライト1の完全な .sb3 として書き出す。"""
    c = Compiler()
    result = c.compile(ir)

    bd_md5, bd_svg = _asset(_BACKDROP)
    cat_md5, cat_svg = _asset(_CAT)

    variables = {vid: [name, 0] for name, vid in result["variables"].items()}
    broadcasts = {bid: name for name, bid in result["broadcasts"].items()}

    stage = {"isStage": True, "name": "Stage", "variables": variables, "lists": {},
             "broadcasts": broadcasts, "blocks": {}, "comments": {}, "currentCostume": 0,
             "costumes": [_costume(bd_md5, "backdrop1", 240, 180)],
             "sounds": [], "volume": 100, "layerOrder": 0,
             "tempo": 60, "videoTransparency": 50, "videoState": "on",
             "textToSpeechLanguage": None}
    sprite = {"isStage": False, "name": "Sprite1", "variables": {}, "lists": {},
              "broadcasts": {}, "blocks": result["blocks"], "comments": {},
              "currentCostume": 0, "costumes": [_costume(cat_md5, "costume1", 30, 30)],
              "sounds": [], "volume": 100, "layerOrder": 1, "visible": True,
              "x": 0, "y": 0, "size": 100, "direction": 90,
              "draggable": False, "rotationStyle": "all around"}
    monitors = [{"id": vid, "mode": "default", "opcode": "data_variable",
                 "params": {"VARIABLE": name}, "spriteName": None, "value": 0,
                 "width": 0, "height": 0, "x": 5, "y": 5 + i * 27, "visible": True,
                 "sliderMin": 0, "sliderMax": 100, "isDiscrete": True}
                for i, (name, vid) in enumerate(result["variables"].items())]

    project = {"targets": [stage, sprite], "monitors": monitors, "extensions": [],
               "meta": {"semver": "3.0.0", "vm": "2.3.0", "agent": "block-chat compiler"}}

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json", json.dumps(project))
        z.writestr(bd_md5 + ".svg", bd_svg)
        z.writestr(cat_md5 + ".svg", cat_svg)
    return result

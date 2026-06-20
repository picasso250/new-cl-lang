struct Value {
    kind_value: i32,
    bool_value: bool,
    num_value: f64,
    str_value: str,
    arr_value: ?*_Array,
    obj_value: ?*_Object
}

struct _Array {
    items: []Value
}

struct _Member {
    key: str,
    value: Value
}

struct _Object {
    entries: []_Member
}

struct _Parser {
    s: str,
    i: i32
}

fun null(): Value {
    ret Value { kind_value: 0, bool_value: false, num_value: 0.0, str_value: "", arr_value: nil, obj_value: nil }
}

fun bool_value(v: bool): Value {
    ret Value { kind_value: 1, bool_value: v, num_value: 0.0, str_value: "", arr_value: nil, obj_value: nil }
}

fun number(v: f64): Value {
    ret Value { kind_value: 2, bool_value: false, num_value: v, str_value: "", arr_value: nil, obj_value: nil }
}

fun string(v: str): Value {
    ret Value { kind_value: 3, bool_value: false, num_value: 0.0, str_value: v, arr_value: nil, obj_value: nil }
}

fun array(): Value {
    ret Value {
        kind_value: 4,
        bool_value: false,
        num_value: 0.0,
        str_value: "",
        arr_value: new _Array { items: []json.Value {} },
        obj_value: nil
    }
}

fun object(): Value {
    ret Value {
        kind_value: 5,
        bool_value: false,
        num_value: 0.0,
        str_value: "",
        arr_value: nil,
        obj_value: new _Object { entries: []json._Member {} }
    }
}

fun kind(v: Value): i32 {
    ret v.kind_value
}

fun as_bool(v: Value): bool {
    if v.kind_value != 1 {
        err "json.as_bool kind mismatch"
    }
    ret v.bool_value
}

fun as_number(v: Value): f64 {
    if v.kind_value != 2 {
        err "json.as_number kind mismatch"
    }
    ret v.num_value
}

fun as_string(v: Value): str {
    if v.kind_value != 3 {
        err "json.as_string kind mismatch"
    }
    ret v.str_value
}

fun array_len(v: Value): i32 {
    if v.kind_value != 4 {
        err "json.array_len kind mismatch"
    }
    let arr = v.arr_value
    if arr != nil {
        ret len(arr.items)
    }
    ret 0
}

fun array_at(v: Value, i: i32): Value {
    if v.kind_value != 4 {
        err "json.array_at kind mismatch"
    }
    let arr = v.arr_value
    if arr != nil {
        if i < 0 || i >= len(arr.items) {
            err "json.array_at index out of range"
        }
        ret (arr.items)[i]
    }
    err "json.array_at missing array"
}

fun array_append(v: Value, item: Value): void {
    if v.kind_value != 4 {
        err "json.array_append kind mismatch"
    }
    let arr = v.arr_value
    if arr != nil {
        arr.items = append(arr.items, item)
        ret
    }
    err "json.array_append missing array"
}

fun object_has(v: Value, key: str): bool {
    if v.kind_value != 5 {
        err "json.object_has kind mismatch"
    }
    let obj = v.obj_value
    if obj != nil {
        for i in 0..len(obj.entries) {
            if (obj.entries)[i].key == key {
                ret true
            }
        }
        ret false
    }
    ret false
}

fun object_get(v: Value, key: str): Value {
    if v.kind_value != 5 {
        err "json.object_get kind mismatch"
    }
    let obj = v.obj_value
    if obj != nil {
        for i in 0..len(obj.entries) {
            if (obj.entries)[i].key == key {
                ret (obj.entries)[i].value
            }
        }
    }
    err "json.object_get missing key"
}

fun object_set(v: Value, key: str, item: Value): void {
    if v.kind_value != 5 {
        err "json.object_set kind mismatch"
    }
    let obj = v.obj_value
    if obj != nil {
        let next = []json._Member {}
        let replaced = false
        for i in 0..len(obj.entries) {
            if (obj.entries)[i].key == key {
                next = append(next, _Member { key: key, value: item })
                replaced = true
            } else {
                next = append(next, (obj.entries)[i])
            }
        }
        if !replaced {
            next = append(next, _Member { key: key, value: item })
        }
        obj.entries = next
        ret
    }
    err "json.object_set missing object"
}

fun parse(s: str): Value {
    let p = new _Parser { s: s, i: 0 }
    _skip_ws(p)
    let v = _parse_value(p)??
    _skip_ws(p)
    if p.i != len(p.s) {
        err "json.parse failed"
    }
    ret v
}

fun stringify(v: Value): str {
    let k = v.kind_value
    if k == 0 {
        ret "null"
    }
    if k == 1 {
        let b = v.bool_value
        if b {
            ret "true"
        }
        ret "false"
    }
    if k == 2 {
        ret str(v.num_value)
    }
    if k == 3 {
        ret _quote(v.str_value)
    }
    if k == 4 {
        let out = "["
        let arr = v.arr_value
        if arr != nil {
            for i in 0..len(arr.items) {
                if i > 0 {
                    out = out + ","
                }
                out = out + stringify((arr.items)[i])
            }
        }
        ret out + "]"
    }
    if k == 5 {
        let out = "{{"
        let obj = v.obj_value
        if obj != nil {
            for i in 0..len(obj.entries) {
                if i > 0 {
                    out = out + ","
                }
                out = out + _quote((obj.entries)[i].key) + ":" + stringify((obj.entries)[i].value)
            }
        }
        ret out + "}}"
    }
    ret "null"
}

fun _parse_value(p: *_Parser): Value {
    _skip_ws(p)
    if p.i >= len(p.s) {
        err "json.parse failed"
    }
    let b = (p.s)[p.i]
    if b == 110 {
        _expect_lit(p, "null")??
        ret null()
    }
    if b == 116 {
        _expect_lit(p, "true")??
        ret bool_value(true)
    }
    if b == 102 {
        _expect_lit(p, "false")??
        ret bool_value(false)
    }
    if b == 34 {
        ret string(_parse_string(p)??)
    }
    if b == 91 {
        ret _parse_array(p)??
    }
    if b == 123 {
        ret _parse_object(p)??
    }
    if b == 45 || _is_digit(b) {
        ret number(_parse_number(p)??)
    }
    err "json.parse failed"
}

fun _parse_array(p: *_Parser): Value {
    p.i = p.i + 1
    let out = array()
    _skip_ws(p)
    if _consume(p, 93) {
        ret out
    }
    for true {
        array_append(out, _parse_value(p)??)??
        _skip_ws(p)
        if _consume(p, 93) {
            ret out
        }
        if !_consume(p, 44) {
            err "json.parse failed"
        }
    }
    ret out
}

fun _parse_object(p: *_Parser): Value {
    p.i = p.i + 1
    let out = object()
    _skip_ws(p)
    if _consume(p, 125) {
        ret out
    }
    for true {
        _skip_ws(p)
        if !_peek(p, 34) {
            err "json.parse failed"
        }
        let key = _parse_string(p)??
        _skip_ws(p)
        if !_consume(p, 58) {
            err "json.parse failed"
        }
        object_set(out, key, _parse_value(p)??)??
        _skip_ws(p)
        if _consume(p, 125) {
            ret out
        }
        if !_consume(p, 44) {
            err "json.parse failed"
        }
    }
    ret out
}

fun _parse_string(p: *_Parser): str {
    if !_consume(p, 34) {
        err "json.parse failed"
    }
    let out = ""
    for p.i < len(p.s) {
        let b = (p.s)[p.i]
        if b == 34 {
            p.i = p.i + 1
            ret out
        }
        if b == 92 {
            p.i = p.i + 1
            if p.i >= len(p.s) {
                err "json.parse failed"
            }
            let e = (p.s)[p.i]
            p.i = p.i + 1
            if e == 34 {
                out = out + "\""
            } else if e == 92 {
                out = out + "\\"
            } else if e == 47 {
                out = out + "/"
            } else if e == 98 {
                out = out + str(rune(8))
            } else if e == 102 {
                out = out + str(rune(12))
            } else if e == 110 {
                out = out + "\n"
            } else if e == 114 {
                out = out + "\r"
            } else if e == 116 {
                out = out + "\t"
            } else if e == 117 {
                out = out + str(rune(_parse_hex4(p)??))
            } else {
                err "json.parse failed"
            }
        } else {
            if b < 32 {
                err "json.parse failed"
            }
            out = out + (p.s)[p.i:(p.i + 1)]
            p.i = p.i + 1
        }
    }
    err "json.parse failed"
}

fun _parse_hex4(p: *_Parser): i32 {
    if p.i + 4 > len(p.s) {
        err "json.parse failed"
    }
    let value = 0
    for n in 0..4 {
        let d = _hex_value((p.s)[p.i])??
        value = value * 16 + d
        p.i = p.i + 1
    }
    ret value
}

fun _parse_number(p: *_Parser): f64 {
    let neg = false
    if _consume(p, 45) {
        neg = true
    }
    if p.i >= len(p.s) {
        err "json.parse failed"
    }

    let value = 0.0
    if _consume(p, 48) {
        value = 0.0
        if p.i < len(p.s) && _is_digit((p.s)[p.i]) {
            err "json.parse failed"
        }
    } else {
        if p.i >= len(p.s) || !_is_digit_1_9((p.s)[p.i]) {
            err "json.parse failed"
        }
        for p.i < len(p.s) && _is_digit((p.s)[p.i]) {
            value = value * 10.0 + f64((p.s)[p.i] - 48)
            p.i = p.i + 1
        }
    }

    if _consume(p, 46) {
        if p.i >= len(p.s) || !_is_digit((p.s)[p.i]) {
            err "json.parse failed"
        }
        let place = 0.1
        for p.i < len(p.s) && _is_digit((p.s)[p.i]) {
            value = value + f64((p.s)[p.i] - 48) * place
            place = place * 0.1
            p.i = p.i + 1
        }
    }

    if p.i < len(p.s) && ((p.s)[p.i] == 101 || (p.s)[p.i] == 69) {
        p.i = p.i + 1
        let exp_neg = false
        if _consume(p, 45) {
            exp_neg = true
        } else if _consume(p, 43) {
            exp_neg = false
        }
        if p.i >= len(p.s) || !_is_digit((p.s)[p.i]) {
            err "json.parse failed"
        }
        let exp = 0
        for p.i < len(p.s) && _is_digit((p.s)[p.i]) {
            exp = exp * 10 + ((p.s)[p.i] - 48)
            p.i = p.i + 1
        }
        let scale = 1.0
        for _n in 0..exp {
            scale = scale * 10.0
        }
        if exp_neg {
            value = value / scale
        } else {
            value = value * scale
        }
    }

    if neg {
        ret 0.0 - value
    }
    ret value
}

fun _quote(s: str): str {
    let out = "\""
    for i in 0..len(s) {
        let b = s[i]
        if b == 34 {
            out = out + "\\\""
        } else if b == 92 {
            out = out + "\\\\"
        } else if b == 8 {
            out = out + "\\b"
        } else if b == 9 {
            out = out + "\\t"
        } else if b == 10 {
            out = out + "\\n"
        } else if b == 12 {
            out = out + "\\f"
        } else if b == 13 {
            out = out + "\\r"
        } else if b < 32 {
            out = out + "\\u00" + _hex_digit(b / 16) + _hex_digit(b % 16)
        } else {
            out = out + s[i:(i + 1)]
        }
    }
    ret out + "\""
}

fun _skip_ws(p: *_Parser): void {
    for p.i < len(p.s) {
        let b = (p.s)[p.i]
        if b == 32 || b == 9 || b == 10 || b == 13 {
            p.i = p.i + 1
        } else {
            ret
        }
    }
}

fun _consume(p: *_Parser, b: i32): bool {
    if p.i < len(p.s) && (p.s)[p.i] == b {
        p.i = p.i + 1
        ret true
    }
    ret false
}

fun _peek(p: *_Parser, b: i32): bool {
    ret p.i < len(p.s) && (p.s)[p.i] == b
}

fun _expect_lit(p: *_Parser, lit: str): void {
    for i in 0..len(lit) {
        if p.i + i >= len(p.s) || (p.s)[p.i + i] != (lit)[i] {
            err "json.parse failed"
        }
    }
    p.i = p.i + len(lit)
}

fun _is_digit(b: i32): bool {
    ret b >= 48 && b <= 57
}

fun _is_digit_1_9(b: i32): bool {
    ret b >= 49 && b <= 57
}

fun _hex_value(b: i32): i32 {
    if b >= 48 && b <= 57 {
        ret b - 48
    }
    if b >= 65 && b <= 70 {
        ret b - 55
    }
    if b >= 97 && b <= 102 {
        ret b - 87
    }
    err "json.parse failed"
}

fun _hex_digit(v: i32): str {
    if v < 10 {
        ret str(rune(48 + v))
    }
    ret str(rune(87 + v))
}


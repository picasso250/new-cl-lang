struct ParseResult { code: str, pos: i32 }

fun skip_space(src: str, pos: i32): i32 {
    while pos < src._len && (src[pos] == 32 || src[pos] == 10 || src[pos] == 9 || src[pos] == 13) {
        pos = pos + 1
    }
    return pos
}

fun read_word(src: str, pos: i32): ParseResult {
    let start = pos
    while pos < src._len && ((65 <= src[pos] && src[pos] <= 90) || (97 <= src[pos] && src[pos] <= 122) || src[pos] == 95 || (48 <= src[pos] && src[pos] <= 57)) {
        pos = pos + 1
    }
    return ParseResult { code: src[start:pos], pos: pos }
}

fun read_number(src: str, pos: i32): ParseResult {
    let start = pos
    while pos < src._len && 48 <= src[pos] && src[pos] <= 57 {
        pos = pos + 1
    }
    return ParseResult { code: src[start:pos], pos: pos }
}

# 解析加法表达式（含加减）
fun parse_expression(src: str, pos: i32): ParseResult {
    let r = parse_term(src, pos)
    let mut code = r.code
    pos = r.pos
    pos = skip_space(src, pos)
    while pos < src._len && (src[pos] == 43 || src[pos] == 45) {
        let op = src[pos]
        pos = pos + 1
        let r2 = parse_term(src, pos)
        if op == 43 {
            code = "(" + code + " + " + r2.code + ")"
        } else {
            code = "(" + code + " - " + r2.code + ")"
        }
        pos = r2.pos
        pos = skip_space(src, pos)
    }
    return ParseResult { code: code, pos: pos }
}

# 解析乘法项（含乘除）
fun parse_term(src: str, pos: i32): ParseResult {
    let r = parse_primary(src, pos)
    let mut code = r.code
    pos = r.pos
    pos = skip_space(src, pos)
    while pos < src._len && (src[pos] == 42 || src[pos] == 47) {
        let op = src[pos]
        pos = pos + 1
        let r2 = parse_primary(src, pos)
        if op == 42 {
            code = "(" + code + " * " + r2.code + ")"
        } else {
            code = "(" + code + " / " + r2.code + ")"
        }
        pos = r2.pos
        pos = skip_space(src, pos)
    }
    return ParseResult { code: code, pos: pos }
}

# 解析基本值
fun parse_primary(src: str, pos: i32): ParseResult {
    pos = skip_space(src, pos)
    if pos >= src._len {
        return ParseResult { code: "", pos: pos }
    }
    let ch = src[pos]
    if 48 <= ch && ch <= 57 {
        return read_number(src, pos)
    }
    if (65 <= ch && ch <= 90) || (97 <= ch && ch <= 122) {
        return read_word(src, pos)
    }
    return ParseResult { code: "", pos: pos }
}

# 解析块 { stmts }
fun parse_block(src: str, pos: i32): ParseResult {
    pos = skip_space(src, pos)
    if pos < src._len && src[pos] == 123 {
        pos = pos + 1
    }
    let mut code = "{\n"
    pos = skip_space(src, pos)
    while pos < src._len && src[pos] != 125 {
        let r = parse_statement(src, pos)
        code = code + r.code
        pos = r.pos
        pos = skip_space(src, pos)
    }
    if pos < src._len && src[pos] == 125 { pos = pos + 1 }
    code = code + "}\n"
    return ParseResult { code: code, pos: pos }
}

# 解析语句
fun parse_statement(src: str, pos: i32): ParseResult {
    pos = skip_space(src, pos)
    if pos >= src._len { return ParseResult { code: "", pos: pos } }
    let ch = src[pos]

    # let 语句
    if (65 <= ch && ch <= 90) || (97 <= ch && ch <= 122) {
        let r = read_word(src, pos)
        let word = r.code
        pos = r.pos

        if word == "let" {
            pos = skip_space(src, pos)
            # 跳过 mut
            if pos < src._len && src[pos] == 109 {
                let r2 = read_word(src, pos)
                if r2.code == "mut" {
                    pos = r2.pos
                    pos = skip_space(src, pos)
                }
            }
            # 读变量名
            let nr = read_word(src, pos)
            let vname = nr.code
            pos = nr.pos
            pos = skip_space(src, pos)
            if pos < src._len && src[pos] == 61 { pos = pos + 1 }
            let er = parse_expression(src, pos)
            return ParseResult { code: "    int " + vname + " = " + er.code + ";\n", pos: er.pos }
        }

        if word == "print" {
            pos = skip_space(src, pos)
            if pos < src._len && src[pos] == 40 { pos = pos + 1 }
            pos = skip_space(src, pos)
            let er = parse_expression(src, pos)
            pos = er.pos
            pos = skip_space(src, pos)
            if pos < src._len && src[pos] == 41 { pos = pos + 1 }
            return ParseResult { code: "    printf(\"%d\\n\", " + er.code + ");\n", pos: pos }
        }

        if word == "if" {
            pos = skip_space(src, pos)
            let cr = parse_expression(src, pos)
            pos = cr.pos
            let block = parse_block(src, pos)
            let mut code = "    if (" + cr.code + ") " + block.code
            pos = block.pos
            pos = skip_space(src, pos)
            # else
            if pos < src._len && src[pos] == 101 {
                let r2 = read_word(src, pos)
                if r2.code == "else" {
                    pos = r2.pos
                    let b2 = parse_block(src, pos)
                    code = code + "    else " + b2.code
                    pos = b2.pos
                }
            }
            return ParseResult { code: code, pos: pos }
        }

        if word == "while" {
            pos = skip_space(src, pos)
            let cr = parse_expression(src, pos)
            pos = cr.pos
            let block = parse_block(src, pos)
            return ParseResult { code: "    while (" + cr.code + ") " + block.code, pos: block.pos }
        }

        # 赋值语句: x = expr
        pos = skip_space(src, pos)
        if pos < src._len && src[pos] == 61 {
            pos = pos + 1
            pos = skip_space(src, pos)
            let er = parse_expression(src, pos)
            return ParseResult { code: "    " + word + " = " + er.code + ";\n", pos: er.pos }
        }
        # 表达式语句
        return ParseResult { code: "    " + word + ";\n", pos: pos }
    }

    # 表达式语句
    let er = parse_expression(src, pos)
    return ParseResult { code: "    " + er.code + ";\n", pos: er.pos }
}

fun main() {
    let src = read_file("input.nc")
    let pos = 0
    let mut out = "#include <stdio.h>\nint main(void) {\n"
    pos = skip_space(src, pos)
    while pos < src._len {
        let r = parse_statement(src, pos)
        out = out + r.code
        pos = skip_space(src, r.pos)
        # 吃掉分号
        if pos < src._len && src[pos] == 59 { pos = pos + 1 }
        pos = skip_space(src, pos)
    }
    out = out + "    return 0;\n}\n"
    write_file("out.c", out)
}

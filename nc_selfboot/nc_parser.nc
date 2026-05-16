# nc_parser.nc — NC 自举编译器（递归下降）
# 支持: let, if/else, while, print, 赋值, 算术/比较表达式
# 使用字符字面量

struct ParseResult { code: str, pos: i32 }

fun skip_space(src: str, pos: i32): i32 {
    while pos < len(src) && (src[pos] == ' ' || src[pos] == '\n' || src[pos] == '\t' || src[pos] == '\r') {
        pos = pos + 1
    }
    return pos
}

fun is_digit(ch: i32): i32 {
    return '0' <= ch && ch <= '9'
}

fun is_alpha(ch: i32): i32 {
    return ('A' <= ch && ch <= 'Z') || ('a' <= ch && ch <= 'z') || ch == '_'
}

fun read_word(src: str, pos: i32): ParseResult {
    let start = pos
    while pos < len(src) && (is_alpha(src[pos]) || is_digit(src[pos])) {
        pos = pos + 1
    }
    return ParseResult { code: src[start:pos], pos: pos }
}

fun read_number(src: str, pos: i32): ParseResult {
    let start = pos
    while pos < len(src) && is_digit(src[pos]) {
        pos = pos + 1
    }
    return ParseResult { code: src[start:pos], pos: pos }
}

# ——— 表达式（优先级链） ———

fun parse_primary(src: str, pos: i32): ParseResult {
    pos = skip_space(src, pos)
    if pos >= len(src) {
        return ParseResult { code: "", pos: pos }
    }
    let ch = src[pos]
    if is_digit(ch) {
        return read_number(src, pos)
    }
    if is_alpha(ch) {
        return read_word(src, pos)
    }
    return ParseResult { code: "", pos: pos }
}

fun parse_mul(src: str, pos: i32): ParseResult {
    let r = parse_primary(src, pos)
    let mut code = r.code
    pos = r.pos
    pos = skip_space(src, pos)
    while pos < len(src) && (src[pos] == '*' || src[pos] == '/') {
        let op = src[pos]
        pos = pos + 1
        let r2 = parse_primary(src, pos)
        if op == '*' { code = "(" + code + " * " + r2.code + ")" }
        else { code = "(" + code + " / " + r2.code + ")" }
        pos = r2.pos
        pos = skip_space(src, pos)
    }
    return ParseResult { code: code, pos: pos }
}

fun parse_add(src: str, pos: i32): ParseResult {
    let r = parse_mul(src, pos)
    let mut code = r.code
    pos = r.pos
    pos = skip_space(src, pos)
    while pos < len(src) && (src[pos] == '+' || src[pos] == '-') {
        let op = src[pos]
        pos = pos + 1
        let r2 = parse_mul(src, pos)
        if op == '+' { code = "(" + code + " + " + r2.code + ")" }
        else { code = "(" + code + " - " + r2.code + ")" }
        pos = r2.pos
        pos = skip_space(src, pos)
    }
    return ParseResult { code: code, pos: pos }
}

fun parse_cmp(src: str, pos: i32): ParseResult {
    let r = parse_add(src, pos)
    let mut code = r.code
    pos = r.pos
    pos = skip_space(src, pos)
    # 检查两字符比较运算符
    let mut op = ""
    if pos + 1 < len(src) && src[pos] == '=' && src[pos+1] == '=' {
        op = "=="; pos = pos + 2
    } else if pos + 1 < len(src) && src[pos] == '!' && src[pos+1] == '=' {
        op = "!="; pos = pos + 2
    } else if pos + 1 < len(src) && src[pos] == '<' && src[pos+1] == '=' {
        op = "<="; pos = pos + 2
    } else if pos + 1 < len(src) && src[pos] == '>' && src[pos+1] == '=' {
        op = ">="; pos = pos + 2
    } else if pos < len(src) && src[pos] == '<' {
        op = "<"; pos = pos + 1
    } else if pos < len(src) && src[pos] == '>' {
        op = ">"; pos = pos + 1
    }
    if op != "" {
        pos = skip_space(src, pos)
        let r2 = parse_add(src, pos)
        code = "(" + code + " " + op + " " + r2.code + ")"
        pos = r2.pos
    }
    return ParseResult { code: code, pos: pos }
}

fun parse_expression(src: str, pos: i32): ParseResult {
    return parse_cmp(src, pos)
}

# ——— 块解析 ———

fun parse_block(src: str, pos: i32): ParseResult {
    pos = skip_space(src, pos)
    if pos < len(src) && src[pos] == '{' {
        pos = pos + 1
    }
    let mut code = "{\n"
    pos = skip_space(src, pos)
    while pos < len(src) && src[pos] != '}' {
        let r = parse_statement(src, pos)
        code = code + r.code
        pos = r.pos
        pos = skip_space(src, pos)
        if pos < len(src) && src[pos] == ';' { pos = pos + 1 }
        pos = skip_space(src, pos)
    }
    if pos < len(src) && src[pos] == '}' { pos = pos + 1 }
    code = code + "}\n"
    return ParseResult { code: code, pos: pos }
}

# ——— 语句 ———

fun parse_statement(src: str, pos: i32): ParseResult {
    pos = skip_space(src, pos)
    if pos >= len(src) { return ParseResult { code: "", pos: pos } }
    let ch = src[pos]
    if ch == '}' { return ParseResult { code: "", pos: pos } }
    if ch == ';' { return ParseResult { code: "", pos: pos + 1 } }

    if is_alpha(ch) {
        let r = read_word(src, pos)
        let word = r.code
        pos = r.pos

        if word == "let" {
            pos = skip_space(src, pos)
            if pos < len(src) && src[pos] == 'm' {
                let r2 = read_word(src, pos)
                if r2.code == "mut" { pos = r2.pos; pos = skip_space(src, pos) }
            }
            let nr = read_word(src, pos)
            let vname = nr.code
            pos = nr.pos
            pos = skip_space(src, pos)
            if pos < len(src) && src[pos] == '=' { pos = pos + 1 }
            let er = parse_expression(src, pos)
            return ParseResult { code: "    int " + vname + " = " + er.code + ";\n", pos: er.pos }
        }

        if word == "print" {
            pos = skip_space(src, pos)
            if pos < len(src) && src[pos] == '(' { pos = pos + 1 }
            pos = skip_space(src, pos)
            let er = parse_expression(src, pos)
            pos = er.pos
            pos = skip_space(src, pos)
            if pos < len(src) && src[pos] == ')' { pos = pos + 1 }
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
            if pos < len(src) && src[pos] == 'e' {
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

        # 赋值
        pos = skip_space(src, pos)
        if pos < len(src) && src[pos] == '=' {
            pos = pos + 1
            pos = skip_space(src, pos)
            let er = parse_expression(src, pos)
            return ParseResult { code: "    " + word + " = " + er.code + ";\n", pos: er.pos }
        }
        return ParseResult { code: "    " + word + ";\n", pos: pos }
    }

    let er = parse_expression(src, pos)
    return ParseResult { code: "    " + er.code + ";\n", pos: er.pos }
}

# ——— 主入口 ———

fun main() {
    let src = read_file("input.nc")
    let pos = 0
    let mut out = "#include <stdio.h>\nint main(void) {\n"
    pos = skip_space(src, pos)
    while pos < len(src) {
        let r = parse_statement(src, pos)
        out = out + r.code
        pos = skip_space(src, r.pos)
        if pos < len(src) && src[pos] == ';' { pos = pos + 1 }
        pos = skip_space(src, pos)
        if pos < len(src) && src[pos] == '}' { break }
    }
    out = out + "    return 0;\n}\n"
    write_file("out.c", out)
}

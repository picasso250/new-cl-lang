# nc_parser.nc — NC 自举编译器（递归下降）
# + fun 解析: fun name(params): type { body }

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

# ——— 表达式 ———

fun parse_primary(src: str, pos: i32): ParseResult {
    pos = skip_space(src, pos)
    if pos >= len(src) { return ParseResult { code: "", pos: pos } }
    let ch = src[pos]
    if ch == '(' {
        pos = pos + 1
        let er = parse_expression(src, pos)
        pos = er.pos
        pos = skip_space(src, pos)
        if pos < len(src) && src[pos] == ')' { pos = pos + 1 }
        return ParseResult { code: "(" + er.code + ")", pos: pos }
    }
    if ch == '"' {
        let start = pos
        pos = pos + 1
        while pos < len(src) && src[pos] != '"' {
            if src[pos] == '\\' && pos + 1 < len(src) { pos = pos + 1 }
            pos = pos + 1
        }
        if pos < len(src) { pos = pos + 1 }
        return ParseResult { code: src[start:pos], pos: pos }
    }
    if is_digit(ch) { return read_number(src, pos) }
    if is_alpha(ch) {
        let r = read_word(src, pos)
        let code = r.code
        pos = r.pos
        pos = skip_space(src, pos)
        # 函数调用
        if pos < len(src) && src[pos] == '(' {
            pos = pos + 1
            pos = skip_space(src, pos)
            let mut args = ""
            if pos < len(src) && src[pos] != ')' {
                let er = parse_expression(src, pos)
                args = er.code
                pos = er.pos
                pos = skip_space(src, pos)
                while pos < len(src) && src[pos] == ',' {
                    pos = pos + 1
                    pos = skip_space(src, pos)
                    let er2 = parse_expression(src, pos)
                    args = args + ", " + er2.code
                    pos = er2.pos
                    pos = skip_space(src, pos)
                }
            }
            pos = skip_space(src, pos)
            if pos < len(src) && src[pos] == ')' { pos = pos + 1 }
            return ParseResult { code: code + "(" + args + ")", pos: pos }
        }
        return ParseResult { code: code, pos: pos }
    }
    return ParseResult { code: "", pos: pos }
}

fun parse_mul(src: str, pos: i32): ParseResult {
    let r = parse_primary(src, pos)
    let mut code = r.code;  pos = r.pos;  pos = skip_space(src, pos)
    while pos < len(src) && (src[pos] == '*' || src[pos] == '/') {
        let op = src[pos];  pos = pos + 1
        let r2 = parse_primary(src, pos)
        if op == '*' { code = "(" + code + " * " + r2.code + ")" }
        else { code = "(" + code + " / " + r2.code + ")" }
        pos = r2.pos;  pos = skip_space(src, pos)
    }
    return ParseResult { code: code, pos: pos }
}

fun parse_add(src: str, pos: i32): ParseResult {
    let r = parse_mul(src, pos)
    let mut code = r.code;  pos = r.pos;  pos = skip_space(src, pos)
    while pos < len(src) && (src[pos] == '+' || src[pos] == '-') {
        let op = src[pos];  pos = pos + 1
        let r2 = parse_mul(src, pos)
        if op == '+' { code = "(" + code + " + " + r2.code + ")" }
        else { code = "(" + code + " - " + r2.code + ")" }
        pos = r2.pos;  pos = skip_space(src, pos)
    }
    return ParseResult { code: code, pos: pos }
}

fun parse_cmp(src: str, pos: i32): ParseResult {
    let r = parse_add(src, pos)
    let mut code = r.code;  pos = r.pos;  pos = skip_space(src, pos)
    let mut op = ""
    if pos + 1 < len(src) && src[pos] == '=' && src[pos+1] == '=' { op = "=="; pos = pos + 2 }
    else if pos + 1 < len(src) && src[pos] == '!' && src[pos+1] == '=' { op = "!="; pos = pos + 2 }
    else if pos + 1 < len(src) && src[pos] == '<' && src[pos+1] == '=' { op = "<="; pos = pos + 2 }
    else if pos + 1 < len(src) && src[pos] == '>' && src[pos+1] == '=' { op = ">="; pos = pos + 2 }
    else if pos < len(src) && src[pos] == '<' { op = "<"; pos = pos + 1 }
    else if pos < len(src) && src[pos] == '>' { op = ">"; pos = pos + 1 }
    if op != "" {
        pos = skip_space(src, pos)
        let r2 = parse_add(src, pos)
        code = "(" + code + " " + op + " " + r2.code + ")";  pos = r2.pos
    }
    return ParseResult { code: code, pos: pos }
}

fun parse_expression(src: str, pos: i32): ParseResult {
    let r = parse_cmp(src, pos)
    let mut code = r.code
    pos = r.pos
    pos = skip_space(src, pos)
    while pos + 1 < len(src) && src[pos] == '&' && src[pos+1] == '&' {
        pos = pos + 2
        let r2 = parse_cmp(src, pos)
        code = "(" + code + " && " + r2.code + ")"
        pos = r2.pos
        pos = skip_space(src, pos)
    }
    while pos + 1 < len(src) && src[pos] == '|' && src[pos+1] == '|' {
        pos = pos + 2
        let r2 = parse_cmp(src, pos)
        code = "(" + code + " || " + r2.code + ")"
        pos = r2.pos
        pos = skip_space(src, pos)
    }
    return ParseResult { code: code, pos: pos }
}

# ——— 类型映射 ———
fun c_type(nc: str): str {
    if nc == "i32" { return "int" }
    if nc == "i64" { return "long long" }
    if nc == "void" { return "void" }
    if nc == "str" { return "str" }
    return nc
}

# ——— 块 ———
fun parse_block(src: str, pos: i32): ParseResult {
    pos = skip_space(src, pos)
    if pos < len(src) && src[pos] == '{' { pos = pos + 1 }
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
    if ch == '#' {
        while pos < len(src) && src[pos] != '\n' { pos = pos + 1 }
        return ParseResult { code: "", pos: pos }
    }
    if ch == ';' { return ParseResult { code: "", pos: pos + 1 } }

    if is_alpha(ch) {
        let r = read_word(src, pos)
        let word = r.code
        pos = r.pos

        if word == "fun" {
            pos = skip_space(src, pos)
            let nr = read_word(src, pos)
            let fname = nr.code
            pos = nr.pos
            # 参数
            pos = skip_space(src, pos)
            let mut params_c = "void"
            if pos < len(src) && src[pos] == '(' {
                pos = pos + 1
                pos = skip_space(src, pos)
                if pos < len(src) && src[pos] != ')' {
                    let pr = read_word(src, pos)
                    let mut pcode = "int " + pr.code
                    pos = pr.pos
                    pos = skip_space(src, pos)
                    if pos < len(src) && src[pos] == ':' {
                        pos = pos + 1
                        pos = skip_space(src, pos)
                        let tr = read_word(src, pos)
                        pcode = c_type(tr.code) + " " + pr.code
                        pos = tr.pos
                    }
                    while pos < len(src) && src[pos] == ',' {
                        pos = pos + 1
                        pos = skip_space(src, pos)
                        let pr2 = read_word(src, pos)
                        let mut p2 = "int " + pr2.code
                        pos = pr2.pos
                        pos = skip_space(src, pos)
                        if pos < len(src) && src[pos] == ':' {
                            pos = pos + 1
                            pos = skip_space(src, pos)
                            let tr2 = read_word(src, pos)
                            p2 = c_type(tr2.code) + " " + pr2.code
                            pos = tr2.pos
                        }
                        pcode = pcode + ", " + p2
                        pos = skip_space(src, pos)
                    }
                    params_c = pcode
                }
                pos = skip_space(src, pos)
                if pos < len(src) && src[pos] == ')' { pos = pos + 1 }
            }
            # 返回类型
            let mut ret = "int"
            pos = skip_space(src, pos)
            if pos < len(src) && src[pos] == ':' {
                pos = pos + 1
                pos = skip_space(src, pos)
                let rr = read_word(src, pos)
                ret = c_type(rr.code)
                pos = rr.pos
            }
            # 体
            pos = skip_space(src, pos)
            let block = parse_block(src, pos)
            let code = ret + " " + fname + "(" + params_c + ") " + block.code
            return ParseResult { code: code, pos: block.pos }
        }

        if word == "struct" {
            while pos < len(src) && src[pos] != '}' { pos = pos + 1 }
            if pos < len(src) { pos = pos + 1 }
            return ParseResult { code: "", pos: pos }
        }

        if word == "return" {
            pos = skip_space(src, pos)
            let er = parse_expression(src, pos)
            return ParseResult { code: "    return " + er.code + ";\n", pos: er.pos }
        }

        if word == "let" {
            pos = skip_space(src, pos)
            if pos < len(src) && src[pos] == 'm' {
                let r2 = read_word(src, pos)
                if r2.code == "mut" { pos = r2.pos; pos = skip_space(src, pos) }
            }
            let vr = read_word(src, pos)
            let vname = vr.code
            pos = vr.pos
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
            if len(er.code) > 0 && er.code[0] == '"' {
                return ParseResult { code: "    printf(" + er.code + "); printf(\"\\n\");\n", pos: pos }
            }
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

# ——— 顶层 ———
fun parse_top(src: str, pos: i32): ParseResult {
    pos = skip_space(src, pos)
    if pos >= len(src) { return ParseResult { code: "", pos: pos } }
    let ch = src[pos]
    if ch == '}' { return ParseResult { code: "", pos: pos } }
    if ch == '#' {
        while pos < len(src) && src[pos] != '\n' { pos = pos + 1 }
        return ParseResult { code: "", pos: pos }
    }
    if ch == ';' { return ParseResult { code: "", pos: pos + 1 } }

    if is_alpha(ch) {
        let r = read_word(src, pos)
        let word = r.code
        let word_start = pos
        pos = r.pos

        if word == "fun" {
            return parse_statement(src, word_start)
        }
        if word == "struct" {
            while pos < len(src) && src[pos] != '}' { pos = pos + 1 }
            if pos < len(src) { pos = pos + 1 }
            return ParseResult { code: "", pos: pos }
        }
        # 其他：从词开始重新解析为语句
        return parse_statement(src, word_start)
    }
    # fallback: non-alpha
    return parse_statement(src, pos)
}

# ——— 主入口 ———
fun main() {
    let src = read_file("input.nc")
    let pos = 0
    let mut out = "#include <stdio.h>\n"
    out = out + "#include <stdlib.h>\n"
    out = out + "#include <string.h>\n"
    out = out + "typedef struct { const char* _ptr; long long _len; } str;\n"
    out = out + "static str __nc_str_cat(str a, str b) {\n"
    out = out + "    char* buf = (char*)malloc(a._len + b._len + 1);\n"
    out = out + "    memcpy(buf, a._ptr, a._len);\n"
    out = out + "    memcpy(buf + a._len, b._ptr, b._len);\n"
    out = out + "    buf[a._len + b._len] = 0;\n"
    out = out + "    str r = {(const char*)buf, a._len + b._len}; return r; }\n"
    out = out + "static int __nc_str_eq(str a, str b) {\n"
    out = out + "    if (a._len != b._len) return 0;\n"
    out = out + "    return strncmp(a._ptr, b._ptr, a._len) == 0; }\n"
    out = out + "static str __nc_read_file(const char* path) {\n"
    out = out + "    FILE* fp = fopen(path, \"rb\");\n"
    out = out + "    if (!fp) { str e = {NULL, 0}; return e; }\n"
    out = out + "    fseek(fp, 0, SEEK_END);\n"
    out = out + "    long long sz = ftell(fp);\n"
    out = out + "    fseek(fp, 0, SEEK_SET);\n"
    out = out + "    char* buf = (char*)malloc(sz + 1);\n"
    out = out + "    fread(buf, 1, sz, fp);\n"
    out = out + "    buf[sz] = 0; fclose(fp);\n"
    out = out + "    str r = {(const char*)buf, sz}; return r; }\n"
    out = out + "static void __nc_write_file(const char* path, str content) {\n"
    out = out + "    FILE* fp = fopen(path, \"w\");\n"
    out = out + "    if (!fp) return;\n"
    out = out + "    fwrite(content._ptr, 1, content._len, fp);\n"
    out = out + "    fclose(fp); }\n"

    pos = skip_space(src, pos)
    while pos < len(src) {
        let r = parse_top(src, pos)
        out = out + r.code
        pos = r.pos
        pos = skip_space(src, pos)
        if pos < len(src) && src[pos] == ';' { pos = pos + 1 }
        pos = skip_space(src, pos)
    }
    write_file("out.c", out)
}

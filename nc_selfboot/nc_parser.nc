struct ParseResult { code: str, pos: i32 }

# 向前跳过空白，返回新位置
fun skip_space(src: str, pos: i32): i32 {
    while pos < src._len && (src[pos] == 32 || src[pos] == 10 || src[pos] == 9 || src[pos] == 13) {
        pos = pos + 1
    }
    return pos
}

# 读取标识符或关键字，返回 (word, new_pos)
fun read_word(src: str, pos: i32): ParseResult {
    let start = pos
    while pos < src._len && ((65 <= src[pos] && src[pos] <= 90) || (97 <= src[pos] && src[pos] <= 122) || src[pos] == 95 || (48 <= src[pos] && src[pos] <= 57)) {
        pos = pos + 1
    }
    return ParseResult { code: src[start:pos], pos: pos }
}

# 读取整数文字，返回 (num_str, new_pos)
fun read_number(src: str, pos: i32): ParseResult {
    let start = pos
    while pos < src._len && 48 <= src[pos] && src[pos] <= 57 {
        pos = pos + 1
    }
    return ParseResult { code: src[start:pos], pos: pos }
}

# 解析语句 → (C 代码, 新位置)
fun parse_statement(src: str, pos: i32): ParseResult {
    pos = skip_space(src, pos)
    if pos >= src._len {
        return ParseResult { code: "", pos: pos }
    }
    let ch = src[pos]
    # print(...)
    if (65 <= ch && ch <= 90) || (97 <= ch && ch <= 122) {
        let r = read_word(src, pos)
        pos = r.pos
        if r.code == "print" {
            pos = skip_space(src, pos)
            if pos < src._len && src[pos] == 40 { pos = pos + 1 }
            pos = skip_space(src, pos)
            let er = parse_expression(src, pos)
            pos = er.pos
            pos = skip_space(src, pos)
            if pos < src._len && src[pos] == 41 { pos = pos + 1 }
            return ParseResult { code: "    printf(\"%d\\n\", " + er.code + ");\n", pos: pos }
        }
    }
    # 默认：表达式语句
    let er = parse_expression(src, pos)
    return ParseResult { code: "    " + er.code + ";\n", pos: er.pos }
}

# 解析表达式 → (C 表达式, 新位置)
fun parse_expression(src: str, pos: i32): ParseResult {
    pos = skip_space(src, pos)
    if pos >= src._len {
        return ParseResult { code: "", pos: pos }
    }
    let ch = src[pos]
    # 整数
    if 48 <= ch && ch <= 57 {
        return read_number(src, pos)
    }
    # 标识符
    if (65 <= ch && ch <= 90) || (97 <= ch && ch <= 122) {
        return read_word(src, pos)
    }
    return ParseResult { code: "", pos: pos }
}

# 主入口
fun main() {
    let src = read_file("input.nc")
    let pos = 0
    let mut out = "#include <stdio.h>\nint main(void) {\n"
    while pos < src._len {
        let r = parse_statement(src, pos)
        pos = r.pos
        out = out + r.code
    }
    out = out + "    return 0;\n}\n"
    write_file("out.c", out)
}

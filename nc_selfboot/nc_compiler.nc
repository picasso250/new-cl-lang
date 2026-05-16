# nc_compiler.nc —— 自举编译器
# 状态机：跟踪 let/print 上下文以正确处理 ;

fun is_digit(ch: i32): i32 {
    if 48 <= ch && ch <= 57 { return 1 }
    return 0
}

fun is_alpha(ch: i32): i32 {
    if (65 <= ch && ch <= 90) || (97 <= ch && ch <= 122) { return 1 }
    return 0
}

fun main() {
    let src = "let x = 10; let y = x + 20; print(y);"
    let mut i = 0
    let mut out = "#include <stdio.h>\nint main(void) {\n"
    let mut in_let = 0

    while i < src._len {
        let ch = src[i]

        if ch == 32 || ch == 10 || ch == 9 || ch == 13 {
            i = i + 1
        } else if is_digit(ch) {
            let start = i
            while i < src._len && is_digit(src[i]) {
                i = i + 1
            }
            out = out + src[start:i]
        } else if is_alpha(ch) {
            let start = i
            while i < src._len && is_alpha(src[i]) {
                i = i + 1
            }
            let word = src[start:i]
            if word == "let" {
                out = out + "    int "
                in_let = 1
            } else if word == "print" {
                out = out + "    printf(\"%d\\n\", "
                in_let = 0
            } else {
                out = out + word
            }
        } else if ch == 61 {
            out = out + " = ("
            i = i + 1
        } else if ch == 59 {
            if in_let {
                out = out + ");\n"
            } else {
                out = out + ";\n"
            }
            in_let = 0
            i = i + 1
        } else if ch == 43 {
            out = out + " + "
            i = i + 1
        } else if ch == 45 {
            out = out + " - "
            i = i + 1
        } else if ch == 42 {
            out = out + " * "
            i = i + 1
        } else if ch == 47 {
            out = out + " / "
            i = i + 1
        } else if ch == 41 {
            out = out + ")"
            i = i + 1
        } else {
            i = i + 1
        }
    }
    out = out + "    return 0;\n}\n"
    write_file("out.c", out)
}

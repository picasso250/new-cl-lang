# nc_compiler.nc —— 自举编译器
# + if/else/==/!=

fun is_digit(ch: i32): i32 {
    if 48 <= ch && ch <= 57 { return 1 }
    return 0
}

fun is_alpha(ch: i32): i32 {
    if (65 <= ch && ch <= 90) || (97 <= ch && ch <= 122) { return 1 }
    return 0
}

fun main() {
    let src = "let x = 10; if x == 10 { print(x); } else { print(0); }"
    let mut i = 0
    let mut out = "#include <stdio.h>\nint main(void) {\n"
    let mut in_let = 0
    let mut after_if = 0

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
                after_if = 0
            } else if word == "print" {
                out = out + "    printf(\"%d\\n\", "
                in_let = 0
                after_if = 0
            } else if word == "if" {
                out = out + "    if ("
                in_let = 0
                after_if = 1
            } else if word == "else" {
                out = out + "else"
                in_let = 0
                after_if = 0
            } else {
                out = out + word
            }
        } else if ch == 61 {
            if i + 1 < src._len && src[i+1] == 61 {
                out = out + " == "
                i = i + 2
            } else {
                out = out + " = ("
                i = i + 1
            }
        } else if ch == 33 {
            if i + 1 < src._len && src[i+1] == 61 {
                out = out + " != "
                i = i + 2
            } else {
                i = i + 1
            }
        } else if ch == 59 {
            if in_let {
                out = out + ");\n"
            } else {
                out = out + ";\n"
            }
            in_let = 0
            i = i + 1
        } else if ch == 123 {
            if after_if {
                out = out + ") {\n"
            } else {
                out = out + " {\n"
            }
            after_if = 0
            i = i + 1
        } else if ch == 125 {
            out = out + "}\n"
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

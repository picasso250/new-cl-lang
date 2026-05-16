# nc_compiler.nc —— 最小自举编译器
# 将 print(整数) 编译为 C printf

fun is_digit(ch: i32): i32 {
    if 48 <= ch && ch <= 57 { return 1 }
    return 0
}

fun is_alpha(ch: i32): i32 {
    if (65 <= ch && ch <= 90) || (97 <= ch && ch <= 122) { return 1 }
    return 0
}

fun main() {
    let src = "print(42)"
    let mut i = 0
    let mut out = "#include <stdio.h>\nint main(void) {\n"
    out = out + "    printf(\"%d\\n\", "

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
            i = i + 1
            while i < src._len && is_alpha(src[i]) {
                i = i + 1
            }
        } else {
            i = i + 1
        }
    }
    out = out + ");\n    return 0;\n}\n"
    write_file("out.c", out)
}

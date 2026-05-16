# nc_compiler.nc —— nc0 自举编译器
# + need_semi 追踪 + fun 识别

fun main() {
    let src = "fun main() { print(1+2) }"
    let mut i = 0
    let mut out = "#include <stdio.h>\n"
    let mut after_if = 0
    let mut need_semi = 0

    while i < src._len {
        let ch = src[i]
        if ch == 32 || ch == 10 || ch == 9 || ch == 13 {
            i = i + 1
        } else if 48 <= ch && ch <= 57 {
            let start = i
            while i < src._len && 48 <= src[i] && src[i] <= 57 { i = i + 1 }
            out = out + src[start:i]
        } else if (65 <= ch && ch <= 90) || (97 <= ch && ch <= 122) || ch == 95 {
            let start = i
            while i < src._len && ((65 <= src[i] && src[i] <= 90) || (97 <= src[i] && src[i] <= 122) || src[i] == 95 || (48 <= src[i] && src[i] <= 57)) {
                i = i + 1
            }
            let word = src[start:i]
            if word == "fun" {
                while i < src._len && (src[i] == 32 || src[i] == 9 || src[i] == 10) { i = i + 1 }
                let fnstart = i
                while i < src._len && ((65 <= src[i] && src[i] <= 90) || (97 <= src[i] && src[i] <= 122) || src[i] == 95 || (48 <= src[i] && src[i] <= 57)) { i = i + 1 }
                let fnname = src[fnstart:i]
                while i < src._len && src[i] != 123 { i = i + 1 }
                i = i + 1
                if fnname == "main" {
                    out = out + "int main(void) {\n"
                } else {
                    out = out + "int " + fnname + "(void) {\n"
                }
            } else if word == "let" {
                out = out + "    int "
                need_semi = 1
            } else if word == "mut" {
            } else if word == "print" {
                out = out + "    printf(\"%d\\n\", "
                need_semi = 1
            } else if word == "if" {
                out = out + "    if ("
                after_if = 1
            } else if word == "else" {
                out = out + "else"
            } else if word == "while" {
                out = out + "    while ("
                after_if = 1
            } else if word == "return" {
                out = out + "    return "
                need_semi = 1
            } else {
                out = out + word
            }
        } else if ch == 61 {
            if i + 1 < src._len && src[i+1] == 61 {
                out = out + " == "
                i = i + 2
            } else {
                out = out + " = "
                need_semi = 1
                i = i + 1
            }
        } else if ch == 60 { out = out + " < "; i = i + 1 }
        else if ch == 62 { out = out + " > "; i = i + 1 }
        else if ch == 59 { out = out + ";\n"; need_semi = 0; i = i + 1 }
        else if ch == 123 {
            if after_if { out = out + ") {\n" }
            else { out = out + " {\n" }
            after_if = 0; i = i + 1
        } else if ch == 125 {
            if need_semi { out = out + ";\n"; need_semi = 0 }
            out = out + "}\n"; i = i + 1
        } else if ch == 43 { out = out + " + "; i = i + 1 }
        else if ch == 45 { out = out + " - "; i = i + 1 }
        else if ch == 42 { out = out + " * "; i = i + 1 }
        else if ch == 47 { out = out + " / "; i = i + 1 }
        else if ch == 41 { out = out + ")"; i = i + 1 }
        else if ch == 46 { out = out + "."; i = i + 1 }
        else if ch == 91 { out = out + "["; i = i + 1 }
        else if ch == 93 { out = out + "]"; i = i + 1 }
        else if ch == 58 { out = out + ":"; i = i + 1 }
        else { i = i + 1 }
    }
    write_file("out.c", out)
}

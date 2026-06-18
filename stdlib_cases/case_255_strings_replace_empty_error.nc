import io
import strings

fun main() {
    if strings.replace_all("abc", "", "x") is err {
        io.println("strings.replace_all empty old")
    }
}

# STDOUT: strings.replace_all empty old

import io
import strings

fun main() {
    try value = strings.replace_all("abc", "", "x") {
        io.println(value)
    } else e {
        io.println("strings.replace_all empty old")
    }
}

# STDOUT: strings.replace_all empty old

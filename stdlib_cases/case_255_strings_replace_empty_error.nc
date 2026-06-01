import io
import strings

fun main() {
    try {
        strings.replace_all("abc", "", "x")
    } catch e {
        io.println(e)
    }
}

# STDOUT: strings.replace_all empty old

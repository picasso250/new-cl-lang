import io
import strconv

fun main() {
    try {
        strconv.parse_i32("12x")
    } catch e {
        io.println(e)
    }
}

# STDOUT: strconv.parse_i32 failed

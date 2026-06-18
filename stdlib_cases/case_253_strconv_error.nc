import io
import strconv

fun main() {
    if strconv.parse_i32("12x") is err {
        io.println("strconv.parse_i32 failed")
    }
}

# STDOUT: strconv.parse_i32 failed

import io
import strconv

fun main() {
    if strconv.parse_i32("12x") is err {
        io.println("strconv.parse_i32 failed")
    }
    if strconv.parse_f32("1e+") is err {
        io.println("strconv.parse_f32 failed")
    }
    if strconv.parse_f64("") is err {
        io.println("empty failed")
    }
    if strconv.parse_f64("+") is err {
        io.println("sign failed")
    }
    if strconv.parse_f64(" 1") is err {
        io.println("space failed")
    }
    if strconv.parse_f64("nan") is err {
        io.println("nan failed")
    }
    if strconv.parse_f64("inf") is err {
        io.println("inf failed")
    }
    if strconv.parse_f64("0x1p2") is err {
        io.println("hex failed")
    }
    if strconv.parse_f64("1_000") is err {
        io.println("underscore failed")
    }
    if strconv.parse_f64("1x") is err {
        io.println("trailing failed")
    }
}

# STDOUT: strconv.parse_i32 failed
# STDOUT: strconv.parse_f32 failed
# STDOUT: empty failed
# STDOUT: sign failed
# STDOUT: space failed
# STDOUT: nan failed
# STDOUT: inf failed
# STDOUT: hex failed
# STDOUT: underscore failed
# STDOUT: trailing failed

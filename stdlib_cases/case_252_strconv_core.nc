import io
import strconv

fun main() {
    io.println(strconv.atoi("42")!!)
    io.println(strconv.parse_i32("-17")!!)
    io.println(strconv.parse_i32("+8")!!)
    io.println(strconv.itoa(99))
    io.println(strconv.format_i32(-5))
    io.println(strconv.parse_f32("0")!!)
    io.println(strconv.parse_f32("+3.5E-2")!!)
    io.println(strconv.format_f32(0.1f32))
    io.println(strconv.parse_f64("12.5")!!)
    io.println(strconv.parse_f64("-.25")!!)
    io.println(strconv.parse_f64("1.")!!)
    io.println(strconv.parse_f64("1e3")!!)
    io.println(strconv.parse_f64("-12.5e2")!!)
    io.println(strconv.format_f64(3.5))
    io.println(strconv.format_f64(0.1))
    io.println(strconv.format_f64(1.2345678901234567))
}

# STDOUT: 42
# STDOUT: -17
# STDOUT: 8
# STDOUT: 99
# STDOUT: -5
# STDOUT: 0
# STDOUT: 0.035
# STDOUT: 0.1
# STDOUT: 12.5
# STDOUT: -0.25
# STDOUT: 1
# STDOUT: 1e+03
# STDOUT: -1.25e+03
# STDOUT: 3.5
# STDOUT: 0.1
# STDOUT: 1.2345678901234567

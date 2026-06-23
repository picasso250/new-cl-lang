import io
import strconv

fun main() {
    try value = strconv.parse_i32("12x") {
        io.println(value)
    } else e {
        io.println("strconv.parse_i32 failed")
    }
    try value = strconv.parse_f32("1e+") {
        io.println(value)
    } else e {
        io.println("strconv.parse_f32 failed")
    }
    try value = strconv.parse_f64("") {
        io.println(value)
    } else e {
        io.println("empty failed")
    }
    try value = strconv.parse_f64("+") {
        io.println(value)
    } else e {
        io.println("sign failed")
    }
    try value = strconv.parse_f64(" 1") {
        io.println(value)
    } else e {
        io.println("space failed")
    }
    try value = strconv.parse_f64("nan") {
        io.println(value)
    } else e {
        io.println("nan failed")
    }
    try value = strconv.parse_f64("inf") {
        io.println(value)
    } else e {
        io.println("inf failed")
    }
    try value = strconv.parse_f64("0x1p2") {
        io.println(value)
    } else e {
        io.println("hex failed")
    }
    try value = strconv.parse_f64("1_000") {
        io.println(value)
    } else e {
        io.println("underscore failed")
    }
    try value = strconv.parse_f64("1x") {
        io.println(value)
    } else e {
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

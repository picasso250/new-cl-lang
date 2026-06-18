fun is_digit_byte(b: i32): bool {
    ret b >= 48 && b <= 57
}

fun digit_byte(b: i32): i32 {
    ret b - 48
}

fun parse_i32(s: str): i32 {
    if len(s) == 0 {
        err "strconv.parse_i32 failed"
    }

    let i = 0
    let neg = false
    if s[0] == 45 {
        neg = true
        i = 1
    } else if s[0] == 43 {
        i = 1
    }
    if i == len(s) {
        err "strconv.parse_i32 failed"
    }

    let limit = 2147483647i64
    if neg {
        limit = 2147483648i64
    }
    let value = 0i64
    for i < len(s) {
        let b = s[i]
        if !is_digit_byte(b) {
            err "strconv.parse_i32 failed"
        }
        let d = i64(digit_byte(b))
        if value > (limit - d) / 10i64 {
            err "strconv.parse_i32 failed"
        }
        value = value * 10i64 + d
        i = i + 1
    }
    if neg {
        ret i32(0i64 - value)
    }
    ret i32(value)
}

fun atoi(s: str): i32 {
    ret parse_i32(s)??
}

fun itoa(n: i32): str {
    ret str(n)
}

fun format_i32(n: i32): str {
    ret str(n)
}

fun parse_f64(s: str): f64 {
    if len(s) == 0 {
        err "strconv.parse_f64 failed"
    }

    let i = 0
    let neg = false
    if s[0] == 45 {
        neg = true
        i = 1
    } else if s[0] == 43 {
        i = 1
    }
    if i == len(s) {
        err "strconv.parse_f64 failed"
    }

    let value = 0.0
    let digits = 0
    for i < len(s) && is_digit_byte(s[i]) {
        value = value * 10.0 + f64(digit_byte(s[i]))
        digits = digits + 1
        i = i + 1
    }
    if i < len(s) && s[i] == 46 {
        i = i + 1
        let place = 0.1
        for i < len(s) && is_digit_byte(s[i]) {
            value = value + f64(digit_byte(s[i])) * place
            place = place * 0.1
            digits = digits + 1
            i = i + 1
        }
    }
    if digits == 0 || i != len(s) {
        err "strconv.parse_f64 failed"
    }
    if neg {
        ret 0.0 - value
    }
    ret value
}

fun format_f64(n: f64): str {
    ret str(n)
}

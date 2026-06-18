fun index(s: str, needle: str): i32 {
    let sub_len = len(needle)
    if sub_len == 0 {
        ret 0
    }
    let s_len = len(s)
    if sub_len > s_len {
        ret -1
    }
    let limit = s_len - sub_len
    for i in 0..(limit + 1) {
        let matched = true
        for j in 0..sub_len {
            if s[i + j] != (needle)[j] {
                matched = false
            }
        }
        if matched {
            ret i
        }
    }
    ret -1
}

fun contains(s: str, needle: str): bool {
    ret index(s, needle) >= 0
}

fun starts_with(s: str, prefix: str): bool {
    let prefix_len = len(prefix)
    if prefix_len > len(s) {
        ret false
    }
    for i in 0..prefix_len {
        if s[i] != (prefix)[i] {
            ret false
        }
    }
    ret true
}

fun ends_with(s: str, suffix: str): bool {
    let suffix_len = len(suffix)
    let s_len = len(s)
    if suffix_len > s_len {
        ret false
    }
    let start = s_len - suffix_len
    for i in 0..suffix_len {
        if s[start + i] != (suffix)[i] {
            ret false
        }
    }
    ret true
}

fun last_index(s: str, needle: str): i32 {
    let sub_len = len(needle)
    let s_len = len(s)
    if sub_len == 0 {
        ret s_len
    }
    if sub_len > s_len {
        ret -1
    }
    let i = s_len - sub_len
    for i >= 0 {
        let matched = true
        for j in 0..sub_len {
            if s[i + j] != (needle)[j] {
                matched = false
            }
        }
        if matched {
            ret i
        }
        i = i - 1
    }
    ret -1
}

fun count(s: str, needle: str): i32 {
    let sub_len = len(needle)
    if sub_len == 0 {
        ret len(s) + 1
    }
    let n = 0
    let i = 0
    for i <= len(s) - sub_len {
        let matched = true
        for j in 0..sub_len {
            if s[i + j] != (needle)[j] {
                matched = false
            }
        }
        if matched {
            n = n + 1
            i = i + sub_len
        } else {
            i = i + 1
        }
    }
    ret n
}

fun repeat(s: str, n: i32): str {
    if n < 0 {
        err "strings.repeat negative count"
    }
    let out = ""
    for i in 0..n {
        out = out + s
    }
    ret out
}

fun replace_all(s: str, old: str, repl: str): str {
    let old_len = len(old)
    if old_len == 0 {
        err "strings.replace_all empty old"
    }
    let out = ""
    let i = 0
    for i < len(s) {
        let matched = false
        if i + old_len <= len(s) {
            matched = true
            for j in 0..old_len {
                if s[i + j] != (old)[j] {
                    matched = false
                }
            }
        }
        if matched {
            out = out + repl
            i = i + old_len
        } else {
            out = out + s[i:(i + 1)]
            i = i + 1
        }
    }
    ret out
}

fun trim_prefix(s: str, prefix: str): str {
    if starts_with(s, prefix) {
        ret s[len(prefix):len(s)]
    }
    ret s
}

fun trim_suffix(s: str, suffix: str): str {
    if ends_with(s, suffix) {
        ret s[0:(len(s) - len(suffix))]
    }
    ret s
}

fun is_space_byte(b: i32): bool {
    ret b == 32 || b == 9 || b == 10 || b == 13
}

fun trim_space(s: str): str {
    let start = 0
    let end = len(s)
    for start < end && is_space_byte(s[start]) {
        start = start + 1
    }
    for end > start && is_space_byte(s[end - 1]) {
        end = end - 1
    }
    ret s[start:end]
}

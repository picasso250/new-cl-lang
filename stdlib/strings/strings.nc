fun index(s: str, needle: str): i32 {
    let sub_len = len(needle)
    if sub_len == 0 {
        return 0
    }
    let s_len = len(s)
    if sub_len > s_len {
        return -1
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
            return i
        }
    }
    return -1
}

fun contains(s: str, needle: str): bool {
    return index(s, needle) >= 0
}

fun starts_with(s: str, prefix: str): bool {
    let prefix_len = len(prefix)
    if prefix_len > len(s) {
        return false
    }
    for i in 0..prefix_len {
        if s[i] != (prefix)[i] {
            return false
        }
    }
    return true
}

fun ends_with(s: str, suffix: str): bool {
    let suffix_len = len(suffix)
    let s_len = len(s)
    if suffix_len > s_len {
        return false
    }
    let start = s_len - suffix_len
    for i in 0..suffix_len {
        if s[start + i] != (suffix)[i] {
            return false
        }
    }
    return true
}

fun last_index(s: str, needle: str): i32 {
    let sub_len = len(needle)
    let s_len = len(s)
    if sub_len == 0 {
        return s_len
    }
    if sub_len > s_len {
        return -1
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
            return i
        }
        i = i - 1
    }
    return -1
}

fun count(s: str, needle: str): i32 {
    let sub_len = len(needle)
    if sub_len == 0 {
        return len(s) + 1
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
    return n
}

fun repeat(s: str, n: i32): str {
    if n < 0 {
        throw "strings.repeat negative count"
    }
    let out = ""
    for i in 0..n {
        out = out + s
    }
    return out
}

fun replace_all(s: str, old: str, repl: str): str {
    let old_len = len(old)
    if old_len == 0 {
        throw "strings.replace_all empty old"
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
    return out
}

fun trim_prefix(s: str, prefix: str): str {
    if starts_with(s, prefix) {
        return s[len(prefix):len(s)]
    }
    return s
}

fun trim_suffix(s: str, suffix: str): str {
    if ends_with(s, suffix) {
        return s[0:(len(s) - len(suffix))]
    }
    return s
}

fun is_space_byte(b: i32): bool {
    return b == 32 || b == 9 || b == 10 || b == 13
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
    return s[start:end]
}

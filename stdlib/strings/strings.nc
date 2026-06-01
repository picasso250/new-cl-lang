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

extern {
    fun nc_argc(): i32 = "__nc_argc"
    fun nc_argv(i: i32): ?*i8 = "__nc_argv"
    fun c_getenv(name: *i8): ?*i8 = "getenv"
    fun c_getcwd(buf: ?*u8, size: i32): ?*u8 = "_getcwd"
    fun c_exit(code: i32): void = "exit"
}

fun args(): []str {
    let out = []str {}
    let n = nc_argc()
    for i in 0..n {
        out = append(out, str(nc_argv(i)))
    }
    return out
}

fun getenv(name: str): str {
    return str(c_getenv(name.c_str()))
}

fun has_env(name: str): bool {
    return c_getenv(name.c_str()) != nil
}

fun cwd(): str {
    let buf = __nc_bytes_alloc(65536u64)
    let ptr = c_getcwd(buf.ptr, 65536)
    if ptr == nil {
        throw "os.cwd failed"
    }
    return str(ptr)
}

fun exit(code: i32) {
    c_exit(code)
}

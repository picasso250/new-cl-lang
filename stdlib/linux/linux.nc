extern {
    fun c_getpid(): i32 = "__nc_linux_getpid"
    fun c_write_bytes(fd: i32, data: ?*u8, len: u64): i64 = "__nc_linux_write"
    fun c_write_str(fd: i32, data: ?*i8, len: u64): i64 = "__nc_linux_write"
}

fun getpid(): i32 {
    return c_getpid()
}

fun write(fd: i32, data: []u8): i64 {
    return c_write_bytes(fd, data.ptr, data.len)
}

fun write_str(fd: i32, data: str): i64 {
    return c_write_str(fd, data.ptr, data.len)
}

extern {
    fun c_fopen(path: *i8, mode: *i8): ?*void = "fopen"
    fun c_fclose(stream: ?*void): i32 = "fclose"
    fun c_fseek(stream: ?*void, offset: i32, origin: i32): i32 = "fseek"
    fun c_ftell(stream: ?*void): i32 = "ftell"
    fun c_fread(ptr: ?*u8, size: u64, count: u64, stream: ?*void): u64 = "fread"
    fun c_fwrite(ptr: ?*i8, size: u64, count: u64, stream: ?*void): u64 = "fwrite"
    fun c_ferror(stream: ?*void): i32 = "ferror"
    fun c_access(path: *i8, mode: i32): i32 = "_access"
    fun c_remove(path: *i8): i32 = "remove"
    fun c_rmdir(path: *i8): i32 = "_rmdir"
    fun c_rename(old_path: *i8, new_path: *i8): i32 = "rename"
    fun c_mkdir(path: *i8): i32 = "_mkdir"
}

fun read_bytes(path: str): []u8 {
    let file = c_fopen(path.c_str(), "rb".c_str())
    if file == nil {
        throw "fs.read_file failed"
    }

    if c_fseek(file, 0, 2) != 0 {
        c_fclose(file)
        throw "fs.read_file failed"
    }
    let size = c_ftell(file)
    if size < 0 {
        c_fclose(file)
        throw "fs.read_file failed"
    }
    if c_fseek(file, 0, 0) != 0 {
        c_fclose(file)
        throw "fs.read_file failed"
    }

    let content = __nc_bytes_alloc(u64(size))
    let n = c_fread(content.ptr, 1u64, u64(size), file)
    if c_ferror(file) != 0 {
        c_fclose(file)
        throw "fs.read_file failed"
    }
    c_fclose(file)
    if n != u64(size) {
        throw "fs.read_file failed"
    }
    return content
}

fun read_file(path: str): str {
    return str(read_bytes(path))
}

fun write_file(path: str, content: str) {
    let file = c_fopen(path.c_str(), "wb".c_str())
    if file == nil {
        throw "fs.write_file failed"
    }
    let n = c_fwrite(content.ptr, 1u64, content.len, file)
    if c_fclose(file) != 0 {
        throw "fs.write_file failed"
    }
    if n != (content.len) {
        throw "fs.write_file failed"
    }
}

fun exists(path: str): bool {
    return c_access(path.c_str(), 0) == 0
}

fun remove(path: str) {
    let c_path = path.c_str()
    if c_remove(c_path) != 0 && c_rmdir(c_path) != 0 {
        throw "fs.remove failed"
    }
}

fun rename(old_path: str, new_path: str) {
    if exists(new_path) {
        throw "fs.rename failed"
    }
    if c_rename(old_path.c_str(), new_path.c_str()) != 0 {
        throw "fs.rename failed"
    }
}

fun mkdir(path: str) {
    if c_mkdir(path.c_str()) != 0 {
        throw "fs.mkdir failed"
    }
}

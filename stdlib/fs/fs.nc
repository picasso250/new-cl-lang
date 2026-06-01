extern {
    fun fopen(path: *i8, mode: *i8): ?*void
    fun fclose(stream: ?*void): i32
    fun fseek(stream: ?*void, offset: i32, origin: i32): i32
    fun ftell(stream: ?*void): i32
    fun fread(ptr: ?*i8, size: u64, count: u64, stream: ?*void): u64
    fun fwrite(ptr: ?*i8, size: u64, count: u64, stream: ?*void): u64
    fun ferror(stream: ?*void): i32
    fun __nc_str_alloc(len: u64): str
    fun __nc_fs_support_exists(path: *i8): i32
    fun __nc_fs_support_remove(path: *i8): i32
    fun __nc_fs_support_rename(old_path: *i8, new_path: *i8): i32
    fun __nc_fs_support_mkdir(path: *i8): i32
}

fun read_file(path: str): str {
    let file = fopen(path.c_str(), "rb".c_str())
    if file == nil {
        throw "fs.read_file failed"
    }

    if fseek(file, 0, 2) != 0 {
        fclose(file)
        throw "fs.read_file failed"
    }
    let size = ftell(file)
    if size < 0 {
        fclose(file)
        throw "fs.read_file failed"
    }
    if fseek(file, 0, 0) != 0 {
        fclose(file)
        throw "fs.read_file failed"
    }

    let content = __nc_str_alloc(u64(size))
    let n = fread(content.ptr, 1u64, u64(size), file)
    if ferror(file) != 0 {
        fclose(file)
        throw "fs.read_file failed"
    }
    fclose(file)
    if n != u64(size) {
        throw "fs.read_file failed"
    }
    return content
}

fun write_file(path: str, content: str) {
    let file = fopen(path.c_str(), "wb".c_str())
    if file == nil {
        throw "fs.write_file failed"
    }
    let n = fwrite(content.ptr, 1u64, content.len, file)
    if fclose(file) != 0 {
        throw "fs.write_file failed"
    }
    if n != (content.len) {
        throw "fs.write_file failed"
    }
}

fun exists(path: str): bool {
    return __nc_fs_support_exists(path.c_str()) != 0
}

fun remove(path: str) {
    if __nc_fs_support_remove(path.c_str()) != 0 {
        throw "fs.remove failed"
    }
}

fun rename(old_path: str, new_path: str) {
    if __nc_fs_support_rename(old_path.c_str(), new_path.c_str()) != 0 {
        throw "fs.rename failed"
    }
}

fun mkdir(path: str) {
    if __nc_fs_support_mkdir(path.c_str()) != 0 {
        throw "fs.mkdir failed"
    }
}

iface Writer { fun write(data: []u8): i32 }
struct File { value: i32 }
fun (f *File) write(data: []u8): i32 { f.value }
fun main() {
    let f: ?*File = nil
    let w: Writer = f
}

# ERROR: let w: expected Writer, got ?*File

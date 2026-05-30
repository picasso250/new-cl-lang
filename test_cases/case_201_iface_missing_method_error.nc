iface Writer { fun write(data: []u8): i32 }
struct File { value: i32 }
fun main() {
    let w: Writer = new File { value: 1 }
}

# ERROR: let w: expected Writer, got *File

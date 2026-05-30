import io

iface Writer { fun write(data: []u8): i32 }

struct File { value: i32 }

fun (f *File) write(data: []u8): i32 {
    f.value + i32(data[0])
}

fun main() {
    let w: Writer = new File { value: 40 }
    io.println(w.write([]u8 { 2u8 }))
}

# STDOUT: 42

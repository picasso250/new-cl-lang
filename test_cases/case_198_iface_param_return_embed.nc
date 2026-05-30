import io

iface Reader { fun read(buf: []u8): i32 }
iface Writer { fun write(data: []u8): i32 }
iface ReadWriter { Reader; Writer }

struct Buffer { value: i32 }

fun (b *Buffer) read(buf: []u8): i32 { b.value }
fun (b *Buffer) write(data: []u8): i32 { b.value + i32(data[0]) }

fun make(): ReadWriter {
    new Buffer { value: 5 }
}

fun use(rw: ReadWriter): i32 {
    rw.read([]u8 { 1u8 }) + rw.write([]u8 { 2u8 })
}

fun main() {
    io.println(use(make()))
}

# STDOUT: 12

import io
# STDOUT: old
# STDOUT: 1
# STDOUT: 2
# STDOUT: 10
# STDOUT: 4
# STDOUT: Z
# STDOUT: 3.5
# STDOUT: 1.25

fun main() {
    let ss = map[str,str]()
    ss["k"] = "old"
    io.println(ss["k"])

    let ib = map[i32,bool]()
    ib[7] = true
    io.println(map_has(ib, 7))

    let bi = map[bool,i32]()
    bi[true] = 1
    bi[false] = 2
    io.println(bi[false])

    let ui = map[u64,i32]()
    ui[99u64] = 10
    io.println(ui[99u64])

    let ri = map[rune,i32]()
    ri['中'] = 4
    io.println(ri['中'])

    let ir = map[i32,rune]()
    ir[1] = 'Z'
    io.println(ir[1])

    let ff = map[f32,f64]()
    ff[1.5f32] = 3.5
    io.println(ff[1.5f32])

    let fi = map[f64,f32]()
    fi[2.5] = 1.25f32
    io.println(fi[2.5])
}

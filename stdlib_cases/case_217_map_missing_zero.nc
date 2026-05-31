import io
# STDOUT: 0
# STDOUT: 0
# STDOUT: 0
# STDOUT: 0
# STDOUT: 0

fun main() {
    let mb = map[str,bool]()
    io.println(mb["missing"])
    let mi = map[str,i32]()
    io.println(mi["missing"])
    let mf = map[str,f64]()
    io.println(mf["missing"])
    let mr = map[str,rune]()
    io.println(i32(mr["missing"]))
    let ms = map[str,str]()
    io.println(len(ms["missing"]))
}

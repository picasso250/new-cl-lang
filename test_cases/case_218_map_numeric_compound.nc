import io
# STDOUT: 8
# STDOUT: ab

fun main() {
    let mi = map[str,i32]()
    mi["x"] = 5
    mi["x"] += 3
    io.println(mi["x"])

    let ms = map[str,str]()
    ms["x"] = "a"
    ms["x"] += "b"
    io.println(ms["x"])
}

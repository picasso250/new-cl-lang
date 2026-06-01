import io

extern {
    fun c_strlen(p: *i8): u64 = "strlen"
}

# STDOUT: 5
fun main() {
    io.println(c_strlen("hello".c_str()))
}

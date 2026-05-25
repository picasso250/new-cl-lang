import io
# STDOUT: 2
fun main() {
    enum Color { Red, Green, Blue }
    let c = Color::Green
    let result = match c {
        Color::Red -> 1
        Color::Green -> 2
        Color::Blue -> 3
    }
    io.println(result)
}

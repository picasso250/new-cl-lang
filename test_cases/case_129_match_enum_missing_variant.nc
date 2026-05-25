import io
# ERROR: match expression: missing enum variants Blue
fun main() {
    enum Color { Red, Green, Blue }
    let c = Color::Red
    let result = match c {
        Color::Red -> 1
        Color::Green -> 2
    }
    io.println(result)
}

# STDOUT: 2
fun main() {
    enum Color { Red, Green, Blue }
    let c = Color::Green
    let result = 0
    switch c {
        Color::Red   -> result = 1
        Color::Green -> result = 2
        Color::Blue  -> result = 3
    }
    print(result)
}

import json
# STDERR: error: json.parse failed
# RC: 1

fun main() {
    json.parse("[1,]")!!
}

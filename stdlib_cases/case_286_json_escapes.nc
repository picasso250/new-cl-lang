import io
import json
# STDOUT: "a\nA\\\""

fun main() {
    io.println(json.stringify(json.parse("\"a\\n\\u0041\\\\\\\"\"")!!))
}

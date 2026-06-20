import io
import json
# STDOUT: 0
# STDOUT: 1
# STDOUT: 1
# STDOUT: -1250
# STDOUT: hi

fun main() {
    io.println(json.kind(json.parse("null")!!))
    io.println(json.kind(json.parse("true")!!))
    io.println(json.as_bool(json.parse("true")!!)??)
    io.println(json.stringify(json.parse("-12.5e2")!!))
    io.println(json.as_string(json.parse("\"hi\"")!!)??)
}

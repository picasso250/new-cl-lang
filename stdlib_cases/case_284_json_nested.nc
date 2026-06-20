import io
import json
# STDOUT: {"a":[1,true,null],"b":{"c":"x"}}
# STDOUT: 3
# STDOUT: x

fun main() {
    let v = json.parse("{{\"a\":[1,true,null],\"b\":{{\"c\":\"x\"}}}}")!!
    io.println(json.stringify(v))
    let a = json.object_get(v, "a")??
    io.println(json.array_len(a)??)
    let b = json.object_get(v, "b")??
    io.println(json.as_string(json.object_get(b, "c")??)??)
}

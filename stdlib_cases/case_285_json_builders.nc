import io
import json
# STDOUT: {"name":"nc","items":[1,2]}
# STDOUT: 1
# STDOUT: 2

fun main() {
    let obj = json.object()
    let arr = json.array()
    json.array_append(arr, json.number(1.0))??
    json.array_append(arr, json.number(2.0))??
    json.object_set(obj, "name", json.string("nc"))??
    json.object_set(obj, "items", arr)??
    io.println(json.stringify(obj))
    io.println(json.object_has(obj, "items")??)
    io.println(json.stringify(json.array_at(arr, 1)??))
}

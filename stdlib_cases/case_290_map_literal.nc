import io

# STDOUT: 1
# STDOUT: 22
# STDOUT: two
# STDOUT: 8
# STDOUT: 0

struct Key { id: i32 }
struct Val { score: i32 }

fun main() {
    let names = map[str,i32]{"a": 1, "b": 2, "b": 22}
    io.println(names["a"])
    io.println(names["b"])

    let nums = map[i32,str]{1: "one", 2: "two"}
    io.println(nums[2])

    let structs = map[Key,Val]{Key { id: 7 }: Val { score: 8 }}
    let got = structs[Key { id: 7 }]
    io.println(got.score)

    let empty = map[str,bool]{}
    io.println(empty.has("missing"))
}

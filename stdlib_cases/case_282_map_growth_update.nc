import io

fun main() {
    let m = map[str,str]()
    m["k0"] = "v0"
    m["k1"] = "v1"
    m["k2"] = "v2"
    m["k3"] = "v3"
    m["k4"] = "v4"
    m["k5"] = "v5"
    m["k6"] = "v6"
    m["k7"] = "v7"
    m["k8"] = "v8"
    m["k9"] = "v9"
    m["k10"] = "v10"
    m["k11"] = "v11"
    m["k12"] = "v12"
    m["k13"] = "v13"
    m["k14"] = "v14"
    m["k15"] = "v15"
    m["k16"] = "v16"
    m["k17"] = "v17"
    m["k18"] = "v18"
    m["k19"] = "v19"
    m["k1"] = "updated"
    io.println(len(m))
    io.println(m.has("k19"))
    io.println(m["k19"])
    io.println(m["k1"])
    io.println(m.has("missing"))
}

# STDOUT: 20
# STDOUT: 1
# STDOUT: v19
# STDOUT: updated
# STDOUT: 0

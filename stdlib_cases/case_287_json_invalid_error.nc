import json
# STDERR: error: json.parse failed
# STDERR: stack:
# STDERR:   at json._parse_value (stdlib/json/json.nc:274:5)
# STDERR:   at json._parse_array (stdlib/json/json.nc:285:27)
# STDERR:   at json._parse_value (stdlib/json/json.nc:266:13)
# STDERR:   at json.parse (stdlib/json/json.nc:189:13)
# STDERR:   at main (stdlib_cases/case_287_json_invalid_error.nc:12:5)
# RC: 1

fun main() {
    json.parse("[1,]")!!
}

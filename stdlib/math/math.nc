extern {
    fun c_sqrt(x: f64): f64 = "__nc_math_sqrt"
    fun c_pow(x: f64, y: f64): f64 = "__nc_math_pow"
    fun c_sin(x: f64): f64 = "__nc_math_sin"
    fun c_cos(x: f64): f64 = "__nc_math_cos"
    fun c_tan(x: f64): f64 = "__nc_math_tan"
    fun c_floor(x: f64): f64 = "__nc_math_floor"
    fun c_ceil(x: f64): f64 = "__nc_math_ceil"
    fun c_round(x: f64): f64 = "__nc_math_round"
    fun c_exp(x: f64): f64 = "__nc_math_exp"
    fun c_log(x: f64): f64 = "__nc_math_log"
}

extern "m" {
    fun _link_libm_marker(): void = "__nc_math_link_libm_marker"
}

fun sqrt(x: f64): f64 { c_sqrt(x) }
fun pow(x: f64, y: f64): f64 { c_pow(x, y) }
fun sin(x: f64): f64 { c_sin(x) }
fun cos(x: f64): f64 { c_cos(x) }
fun tan(x: f64): f64 { c_tan(x) }
fun floor(x: f64): f64 { c_floor(x) }
fun ceil(x: f64): f64 { c_ceil(x) }
fun round(x: f64): f64 { c_round(x) }
fun exp(x: f64): f64 { c_exp(x) }
fun log(x: f64): f64 { c_log(x) }

fun pi(): f64 { 3.141592653589793 }
fun e(): f64 { 2.718281828459045 }

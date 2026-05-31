import io
import strings

fun main() {
    io.println(strings.contains("hello", "ell"))
    io.println(strings.contains("hello", "zz"))
    io.println(strings.starts_with("hello", "he"))
    io.println(strings.starts_with("hello", "lo"))
    io.println(strings.ends_with("hello", "lo"))
    io.println(strings.ends_with("hello", "he"))
    io.println(strings.index("hello hello", "lo"))
    io.println(strings.index("hello", "zz"))
    io.println(strings.contains("hello", ""))
    io.println(strings.starts_with("hello", ""))
    io.println(strings.ends_with("hello", ""))
    io.println(strings.index("hello", ""))
    io.println(strings.index("中x中", "x"))
}

# STDOUT: 1
# STDOUT: 0
# STDOUT: 1
# STDOUT: 0
# STDOUT: 1
# STDOUT: 0
# STDOUT: 3
# STDOUT: -1
# STDOUT: 1
# STDOUT: 1
# STDOUT: 1
# STDOUT: 0
# STDOUT: 3

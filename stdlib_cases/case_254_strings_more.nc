import io
import strings

fun main() {
    io.println(strings.last_index("hello hello", "lo"))
    io.println(strings.last_index("hello", ""))
    io.println(strings.count("aaaa", "aa"))
    io.println(strings.count("abc", ""))
    io.println(strings.repeat("ab", 3))
    io.println(strings.replace_all("a-b-a", "a", "xy"))
    io.println(strings.trim_prefix("foobar", "foo"))
    io.println(strings.trim_suffix("foobar", "bar"))
    io.println(strings.trim_space(" \t\nok\r\n"))
}

# STDOUT: 9
# STDOUT: 5
# STDOUT: 2
# STDOUT: 4
# STDOUT: ababab
# STDOUT: xy-b-xy
# STDOUT: bar
# STDOUT: foo
# STDOUT: ok

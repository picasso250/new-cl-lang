iface A { fun value(): i32 }
iface B { fun value(): str }
iface C { A; B }

# ERROR: conflicting method value

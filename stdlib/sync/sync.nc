extern {
    fun nc_mutex_alloc(): *u8 = "__nc_mutex_alloc"
    fun nc_mutex_free(m: *u8): void = "__nc_mutex_free"
    fun nc_mutex_lock(m: *u8): void = "__nc_mutex_lock"
    fun nc_mutex_unlock(m: *u8): void = "__nc_mutex_unlock"
}

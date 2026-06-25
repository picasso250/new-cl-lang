# case_402_mutex_basic: spawn + sync.Mutex = no deadlock
import sync

fun main() {
    let mu = sync.nc_mutex_alloc()
    spawn fun() {
        sync.nc_mutex_lock(mu)
        sync.nc_mutex_unlock(mu)
    }
    spawn fun() {
        sync.nc_mutex_lock(mu)
        sync.nc_mutex_unlock(mu)
    }
}

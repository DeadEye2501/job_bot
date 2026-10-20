"""Блокировка байта lock-файла Windows."""


def lock_file(fd: int) -> None:
    import msvcrt

    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

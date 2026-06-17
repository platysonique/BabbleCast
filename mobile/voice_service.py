"""Android foreground service entry — keeps mic capture eligible while connected."""


def main() -> None:
    import time

    while True:
        time.sleep(3600)

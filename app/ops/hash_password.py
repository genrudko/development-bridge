from __future__ import annotations

import getpass
import sys

from app.ops.auth import hash_password


def main() -> None:
    password = getpass.getpass("Enter operator password: ")
    confirm = getpass.getpass("Confirm operator password: ")
    if not password:
        sys.stderr.write("Password cannot be empty.\n")
        sys.exit(1)
    if password != confirm:
        sys.stderr.write("Passwords do not match.\n")
        sys.exit(1)
    hashed = hash_password(password)
    sys.stdout.write(hashed + "\n")


if __name__ == "__main__":
    main()

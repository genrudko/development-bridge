import pytest
from unittest.mock import patch
import sys
from io import StringIO

from app.ops.auth import hash_password, verify_password
from app.ops.hash_password import main as hash_password_main


def test_hash_password_and_verify_success():
    pw = "CorrectHorseBatteryStaple!123"
    hashed = hash_password(pw)
    assert hashed.startswith("scrypt$16384$8$1$")
    assert verify_password(pw, hashed) is True


def test_verify_password_wrong_password():
    pw = "SuperSecret123"
    hashed = hash_password(pw)
    assert verify_password("WrongPassword123", hashed) is False
    assert verify_password("", hashed) is False


@pytest.mark.parametrize("invalid_hash", [
    "",
    "plainpassword",
    "scrypt$invalid$8$1$salt$digest",
    "scrypt$16384$8$1$bad_salt!$digest",
    "scrypt$16384$8$1$salt$",
    "bcrypt$12$salt$digest",
    "scrypt$16384$8$1",
])
def test_verify_password_malformed_hashes_fail_safely(invalid_hash):
    assert verify_password("password", invalid_hash) is False


def test_hash_password_cli_matching():
    with patch("getpass.getpass", side_effect=["my-pass", "my-pass"]), \
         patch("sys.stdout", new_callable=StringIO) as fake_out:
        hash_password_main()
        output = fake_out.getvalue().strip()
        assert output.startswith("scrypt$16384$8$1$")
        assert verify_password("my-pass", output) is True


def test_hash_password_cli_mismatch():
    with patch("getpass.getpass", side_effect=["my-pass", "other-pass"]), \
         patch("sys.stderr", new_callable=StringIO) as fake_err, \
         pytest.raises(SystemExit) as exc:
        hash_password_main()
    assert exc.value.code == 1
    assert "Passwords do not match" in fake_err.getvalue()


def test_hash_password_cli_empty():
    with patch("getpass.getpass", side_effect=["", ""]), \
         patch("sys.stderr", new_callable=StringIO) as fake_err, \
         pytest.raises(SystemExit) as exc:
        hash_password_main()
    assert exc.value.code == 1
    assert "cannot be empty" in fake_err.getvalue()

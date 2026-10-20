"""Deliberately unsafe code so the security checks have something to find."""

import subprocess

# Synthetic, obviously fake credential for the example.
DATABASE_PASSWORD = "example-not-a-real-password"


def ping(host):
    # B602/S602: shell=True with interpolated input -> command injection risk.
    return subprocess.call("ping -c 1 " + host, shell=True)

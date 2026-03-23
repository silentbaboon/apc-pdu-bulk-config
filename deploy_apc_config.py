#!/usr/bin/env python3
"""
APC PDU Bulk Config Deployer
-----------------------------
For each PDU, this script:
  1. Connects via SSH, handling the forced first-login password change if present
  2. Enables FTP via the APC CLI
  3. Pulls the existing config.ini from the PDU via FTP
  4. Modifies only the keys defined in ENFORCED_SETTINGS
  5. Pushes the updated config.ini back via FTP

All other settings in the PDU's config are left completely untouched.

Requirements:
    - Python 3.x (no pip installs needed — all standard library)
    - expect (system package): dnf install expect -y

Usage:
    python3 deploy_apc_config.py
"""

import os
import re
import time
import ftplib
import subprocess
import tempfile
from pathlib import Path

# ---------------------------------------------
# CONFIG - edit these before running
# ---------------------------------------------

PDU_LIST_FILE      = "pdu_list.txt"    # One IP address per line
PDU_USERNAME       = "apc"             # NMC username
PDU_PASSWORD       = "apc"             # Current/default password
PDU_NEW_PASSWORD   = "YourPassword"     # New password to set on all PDUs
REMOTE_CONFIG_PATH = "config.ini"      # Path to config.ini on the PDU

# Only these keys will be modified. Everything else in the PDU's
# existing config.ini is preserved exactly as-is.
ENFORCED_SETTINGS = {
    "SystemID": {
        "Location": "YourLocation",
        "Contact": "YourContact",
    },
    "NetworkSNMP": {
        "Access": "enabled",                 # Enable SNMPv1
        "AccessControl1Community": "public", # Community string
        "AccessControl1AccessType": "Read",  # Access type
        "AccessControl1NMS": "0.0.0.0",      # Allow all NMS (change if needed)
    },
}

# Path to the expect script (must be in the same directory as this script)
EXPECT_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apc_setup.exp")

# ---------------------------------------------
# FUNCTIONS
# ---------------------------------------------

def run_expect(ip: str) -> str:
    """
    Run the expect script to handle SSH login, first-login password
    change, and FTP enable. Returns the password to use for FTP.
    """
    location = ENFORCED_SETTINGS.get("SystemID", {}).get("Location", "")
    contact  = ENFORCED_SETTINGS.get("SystemID", {}).get("Contact", "")
    result = subprocess.run(
        ["expect", EXPECT_SCRIPT, ip, PDU_PASSWORD, PDU_NEW_PASSWORD, location, contact],
        capture_output=True,
        text=True,
        timeout=120,
    )
    print(f"    [{ip}] Expect output: {result.stdout.strip()}")
    if result.returncode != 0:
        raise RuntimeError(f"Expect script failed: {result.stderr.strip()}")

    # Determine which password to use for FTP:
    # - If first-login password change occurred, use new password
    # - If logged in with new password directly (Permission denied on first try), use new password
    # - Otherwise the default password worked, use that
    if "Enter current password:" in result.stdout or "Permission denied" in result.stdout:
        return PDU_NEW_PASSWORD
    return PDU_PASSWORD


def apply_changes(config_text: str, settings: dict) -> str:
    """
    Walk the existing config line by line.
    Only replace the value of keys that appear in ENFORCED_SETTINGS.
    All other lines are written back exactly as they were.
    """
    lines = config_text.splitlines()
    current_section = None
    result = []

    for line in lines:
        section_match = re.match(r'^\[(.+)\]', line)
        if section_match:
            current_section = section_match.group(1)
            result.append(line)
            continue

        if current_section and current_section in settings:
            key_match = re.match(r'^(\w+)\s*=', line)
            if key_match:
                key = key_match.group(1)
                if key in settings[current_section]:
                    line = f"{key}={settings[current_section][key]}"

        result.append(line)

    return "\n".join(result)


def process_pdu(ip: str) -> bool:
    """
    Connect to a PDU, handle first-login password change if needed,
    enable FTP, then pull, modify, and push the config via FTP.
    Returns True on success, False on failure.
    """
    try:
        # Step 1: Run expect script to handle SSH login, password change, FTP enable
        print(f"    [{ip}] Running expect script (SSH + password change + FTP enable)...")
        ftp_password = run_expect(ip)
        print(f"    [{ip}] Expect script complete. Waiting for PDU to reboot...")
        time.sleep(60)  # PDU reboots after ftp enable — wait for it to come back

        # Step 2: Pull config, modify it, push it back via FTP
        print(f"    [{ip}] Transferring config via FTP...")
        with tempfile.TemporaryDirectory() as tmpdir:
            local_config = os.path.join(tmpdir, "config.ini")

            ftp = ftplib.FTP()
            ftp.connect(ip, 21, timeout=10)
            ftp.login(PDU_USERNAME, ftp_password)

            # Pull config.ini
            with open(local_config, "wb") as f:
                ftp.retrbinary(f"RETR {REMOTE_CONFIG_PATH}", f.write)
            print(f"    [{ip}] Config pulled.")

            # Apply changes
            original = Path(local_config).read_text()
            modified = apply_changes(original, ENFORCED_SETTINGS)
            Path(local_config).write_text(modified)

            # Push modified config.ini back
            with open(local_config, "rb") as f:
                ftp.storbinary(f"STOR {REMOTE_CONFIG_PATH}", f)
            print(f"    [{ip}] Config pushed.")

            ftp.quit()

        print(f"  [OK]   {ip} — config updated successfully")
        return True

    except Exception as e:
        import traceback
        print(f"  [FAIL] {ip} — {e}")
        traceback.print_exc()
        return False


def load_pdu_list(filepath: str) -> list:
    """Load IPs from a text file, one per line. Skips blank lines and comments."""
    with open(filepath) as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.startswith("#")
        ]


# ---------------------------------------------
# MAIN
# ---------------------------------------------

def main():
    print("Settings that will be modified on each PDU:")
    print("-" * 40)
    for section, keys in ENFORCED_SETTINGS.items():
        print(f"[{section}]")
        for key, value in keys.items():
            print(f"  {key}={value}")
    print("-" * 40)

    pdu_list_path = Path(PDU_LIST_FILE)
    if not pdu_list_path.exists():
        print(f"\nERROR: PDU list file not found: {PDU_LIST_FILE}")
        return

    pdus = load_pdu_list(PDU_LIST_FILE)
    print(f"\nProcessing {len(pdus)} PDU(s)...\n")

    success = 0
    failed  = 0

    for ip in pdus:
        if process_pdu(ip):
            success += 1
        else:
            failed += 1

    print(f"\nDone. {success} succeeded, {failed} failed.")


if __name__ == "__main__":
    main()

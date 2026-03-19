# apc-pdu-bulk-config

A Python + Expect tool for bulk provisioning APC NetShelter Rack PDUs running Network Management Car
d (NMC) firmware v3.x.

Automates the following across a list of PDUs in a single run:
- First-login forced password change
- Setting system Location and Contact via CLI
- Enabling FTP
- Pushing a modified `config.ini` via FTP (preserving all existing settings)
- Rebooting to apply changes

## Requirements

**No pip installs required** — the Python script uses only the standard library.

The only external dependency is `expect`:

```bash
# RHEL/Rocky/CentOS
dnf install expect -y

# Debian/Ubuntu
apt-get install expect -y
```

## Files

| File | Description |
|------|-------------|
| `deploy_apc_config.py` | Main Python script — reads PDU list, runs expect, transfers config |
| `apc_setup.exp` | Expect script — handles SSH login, password change, CLI commands, reboot |
| `pdu_list.txt` | One PDU IP address per line |

## Setup

1. Clone the repo:
```bash
git clone https://github.com/silentbaboon/apc-pdu-bulk-config.git
cd apc-pdu-bulk-config
```

2. Install expect:
```bash
dnf install expect -y
```

3. Make the expect script executable:
```bash
chmod +x apc_setup.exp
```

4. Edit `deploy_apc_config.py` and update the config section at the top:
```python
PDU_LIST_FILE    = "pdu_list.txt"   # One IP address per line
PDU_USERNAME     = "apc"            # NMC SSH username
PDU_PASSWORD     = "apc"            # Current/default password
PDU_NEW_PASSWORD = "yourPassword"   # New password to set on all PDUs
```

5. Update `ENFORCED_SETTINGS` with your desired values:
```python
ENFORCED_SETTINGS = {
    "SystemID": {
        "Location": "YOUR_LOCATION",  # e.g. "Server Room A"
        "Contact":  "YOUR_CONTACT",   # e.g. "Not Set"
    },
    "NetworkSNMP": {
        "Access":                   "enabled",
        "AccessControl1Community":  "YOUR_COMMUNITY_STRING",  # e.g. "public"
        "AccessControl1AccessType": "Read",
        "AccessControl1NMS":        "0.0.0.0",
    },
}
```

6. Populate `pdu_list.txt` with your PDU IP addresses:
```
192.168.1.10
192.168.1.11
192.168.1.12
# Lines starting with # are ignored
```

7. Run the script:
```bash
python3 deploy_apc_config.py
```

## How It Works

For each PDU in the list the script:

1. Runs `apc_setup.exp` which SSHs into the PDU, handles the forced first-login password change if p
resent, sets Location and Contact via the APC CLI, enables FTP, and reboots
2. Waits 60 seconds for the PDU to come back online
3. Connects via FTP, pulls the existing `config.ini`, modifies only the keys defined in `ENFORCED_SE
TTINGS`, and pushes it back — all other settings are preserved
4. SSHs back in and reboots again to apply the pushed config

## Compatibility

Tested on:
- APC NetShelter APDU11000 Series Rack PDUs
- NMC firmware AOS v3.0.0.12 / APP v3.0.0.5
- Rocky Linux 10

## Notes

- The script is safe to re-run — if a PDU has already had its password changed it will skip the pass
word change step automatically
- FTP is disabled by default on APC NMCs and is enabled temporarily by this script to transfer the c
onfig
- The PDU reboots twice during provisioning — once after the CLI changes and once after the config p
ush. Total time per PDU is approximately 2-3 minutes

## License

MIT — see [LICENSE](LICENSE)

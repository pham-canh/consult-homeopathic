#!/usr/bin/env python3
"""Create a dedicated Vultr VM for this app.

Reads a Vultr API key from VULTR_API_KEY or ~/.vultr_api_key. Creates (or reuses)
an SSH key entry and a firewall group (22/80/443), then creates an Ubuntu 24.04
instance. Writes `.deploy-server.json` at the repo root for the deploy script.

This script only touches resources labelled `consult-homeopathic`. It never
modifies another project's server or service.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.vultr.com/v2"
ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / ".deploy-server.json"
DEFAULT_LABEL = "consult-homeopathic"
DEFAULT_FIREWALL = "consult-homeopathic-web"


def api_key() -> str:
    key = os.environ.get("VULTR_API_KEY", "").strip()
    if key:
        return key
    path = Path.home() / ".vultr_api_key"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    raise SystemExit("Set VULTR_API_KEY or put the key in ~/.vultr_api_key")


def request(method: str, path: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        API + path, data=body, method=method,
        headers={"Authorization": "Bearer " + api_key(),
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise SystemExit(f"Vultr API {method} {path} -> HTTP {exc.code}: {detail}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach the Vultr API: {exc.reason}")


def public_key() -> str:
    explicit = os.environ.get("VULTR_SSH_PUBLIC_KEY", "").strip()
    if explicit:
        return explicit
    for name in ("id_ed25519.pub", "id_rsa.pub"):
        path = Path.home() / ".ssh" / name
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    raise SystemExit("No public key found. Set VULTR_SSH_PUBLIC_KEY or create "
                     "~/.ssh/id_ed25519.pub")


def ensure_ssh_key(name: str) -> str:
    key = public_key()
    rows = request("GET", "/ssh-keys?per_page=500").get("ssh_keys", [])
    for row in rows:
        if row.get("ssh_key", "").strip() == key:
            return row["id"]
    created = request("POST", "/ssh-keys", {"name": name, "ssh_key": key})
    return created["ssh_key"]["id"]


def ensure_firewall(name: str) -> str:
    rows = request("GET", "/firewalls?per_page=500").get("firewalls", [])
    for row in rows:
        if row.get("description") == name:
            return row["id"]
    rules = [
        {"protocol": "tcp", "port": "22", "ip_type": "v4",
         "subnet": "0.0.0.0", "subnet_size": 0, "notes": "SSH"},
        {"protocol": "tcp", "port": "80", "ip_type": "v4",
         "subnet": "0.0.0.0", "subnet_size": 0, "notes": "Caddy HTTP"},
        {"protocol": "tcp", "port": "443", "ip_type": "v4",
         "subnet": "0.0.0.0", "subnet_size": 0, "notes": "Caddy HTTPS"},
    ]
    created = request("POST", "/firewalls",
                      {"description": name, "rules": rules})
    return created["firewall"]["id"]


def find_os() -> int:
    rows = request("GET", "/os?per_page=500").get("os", [])
    for row in rows:
        name = row.get("name", "")
        if name.startswith("Ubuntu 24.04") and row.get("arch") == "x64":
            return int(row["id"])
    raise SystemExit("Ubuntu 24.04 x64 is not available in this account")


def find_plan(region: str, wanted: str) -> str:
    rows = request("GET", "/plans?per_page=500").get("plans", [])
    available = [row for row in rows
                 if not row.get("regions") or region in row["regions"]]
    ids = {row["id"] for row in available}
    if wanted in ids:
        return wanted
    for row in available:
        if row.get("type") == "vc2" and row.get("ram", 0) >= 2048:
            return row["id"]
    raise SystemExit(f"Plan {wanted} is not available in {region}")


def find_existing(label: str) -> dict | None:
    rows = request("GET", "/instances?per_page=500").get("instances", [])
    for row in rows:
        if row.get("label") == label and row.get("status") != "destroyed":
            return row
    return None


def wait_for_ip(instance_id: str, timeout: int = 420) -> str:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        row = request("GET", f"/instances/{instance_id}").get("instance", {})
        last = row.get("status", "unknown")
        ip = row.get("main_ip", "")
        if last == "active" and ip and ip != "0.0.0.0":
            return ip
        print(f"  waiting: status={last} ip={ip or '-'}", flush=True)
        time.sleep(6)
    raise SystemExit(f"Instance did not become active (last status: {last})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision the app's Vultr VM")
    parser.add_argument("--region", default=os.environ.get("VULTR_REGION", "sgp"))
    parser.add_argument("--plan", default=os.environ.get("VULTR_PLAN", "vc2-1c-2gb"))
    parser.add_argument("--label", default=os.environ.get("VULTR_LABEL", DEFAULT_LABEL))
    parser.add_argument("--new", action="store_true",
                        help="create another instance even if the label exists")
    args = parser.parse_args()

    existing = None if args.new else find_existing(args.label)
    if existing:
        instance = existing
        print(f"Reusing instance {instance['id']} ({instance.get('main_ip')})")
    else:
        key_id = ensure_ssh_key(args.label)
        firewall_id = ensure_firewall(DEFAULT_FIREWALL)
        os_id = find_os()
        plan_id = find_plan(args.region, args.plan)
        print(f"Creating {plan_id} in {args.region} with OS {os_id} …")
        payload = {
            "region": args.region,
            "plan": plan_id,
            "os_id": os_id,
            "label": args.label,
            "hostname": args.label,
            "sshkey_id": [key_id],
            "firewall_group_id": firewall_id,
            "enable_ipv6": False,
            "backups": "disabled",
            "activation_email": False,
            "ddos_protection": False,
        }
        created = request("POST", "/instances", payload)
        instance = created["instance"]

    ip = wait_for_ip(instance["id"])
    domain = f"{args.label}.{ip}.sslip.io"
    state = {
        "id": instance["id"],
        "label": args.label,
        "region": args.region,
        "ip": ip,
        "domain": domain,
        "url": f"https://{domain}",
    }
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

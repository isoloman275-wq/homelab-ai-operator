# Worked Example — Windows repair over PXE (2026-09-02)

Lab session: client PC with a blown GPU, corrupted NTFS, no USB stick. Repaired entirely over the network. All specifics below are THAT session's values — substitute your own.

## Topology

- PXE server: Windows host `main-node` (MAIN-NODE's Windows side — WSL is NAT'd and CANNOT serve LAN broadcasts; always run the PXE server from a machine natively on the LAN).
- Patient: DHCP-leased `patient-host`.
- Existing DHCP server: the router (`router`) → hence proxydhcp mode.
- Second disk in patient (931GB data NTFS, `sdb`) — explicitly left untouched; confirm with the owner before touching any disk beyond the boot disk.

## Setup performed

```
dir: C:\Users\Admin\pxe\server
files: pxesrv.exe (from erwan2212/tinypxeserver pxesrv.zip)
       netboot.xyz.kpxe + netboot.xyz.efi (into files/ TFTP root)
```

config.ini edits (CRLF — python string .replace landed once and missed once due to line endings; verify with grep after editing):

- `proxydhcp=1` (router owns DHCP)
- `start=1` (auto-online daemons)
- `filename=netboot.xyz.kpxe`
- `00007=netboot.xyz.efi` and `00009=netboot.xyz.efi` under `[arch]`
- web port moved off 80 → 8088

Firewall (PowerShell, admin):

```
New-NetFirewallRule -DisplayName pxe-tftp -Direction Inbound -Protocol UDP -LocalPort 69 -Action Allow
New-NetFirewallRule -DisplayName pxe-proxydhcp -Direction Inbound -Protocol UDP -LocalPort 4011 -Action Allow
New-NetFirewallRule -DisplayName pxe-http -Direction Inbound -Protocol TCP -LocalPort 8088 -Action Allow
```

Verified bound: `Get-NetUDPEndpoint` showed pxesrv PID owning 67, 69, 4011 on main-node.

## Monitoring (run from the WSL agent box)

Sweep watcher + raw DHCP sniffer (see SKILL.md Phase 1). Patient first appeared at `patient-host` and flapped on/off the wire repeatedly while PXE-looping — repeated new-host hits for the same IP were the signal, not one-shot events.

## Remote control

On patient (SystemRescue console):

```
passwd                  # set root password
systemctl start sshd
ss -tlnp | grep sshd    # showed 0.0.0.0:22 but outside was still blocked
nft flush ruleset       # <- the missing step; SystemRescue default ruleset drops inbound 22
```

From agent box:

```
sshpass -p <pw> ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@patient-host '<cmd>'
```

## Repair transcript (condensed)

- `lsblk`: sda 238.5G (sda1 50M ntfs, sda2 237.9G ntfs, sda3 509M ntfs), sdb 931.5G ntfs (data — untouched).
- `smartctl -H /dev/sda` → PASSED. Reallocated=0, Uncorrect=0, Wear_Leveling=19, 9787 power-on hours.
- `mount -o ro /dev/sda2 /mnt/win` → full tree readable.
- `ntfsfix -d /dev/sda2`: `$MFTMirr does not match $MFT (record 3)` → corrected; journal emptied; `Failed to sync device` warning mid-run; final `processed successfully`. RW test (touch+rm) OK.
- `ntfsfix` on sda1 + sda3: clean.
- sda1 identity: `file -s /dev/sda1` → `NTFS ... contains bootstrap BOOTMGR` (System Reserved; vfat mount failing here is EXPECTED).
- `rm /mnt/win/hiberfil.sys` (6.8GB, pre-repair timestamp) — killed the fast-startup resume-into-dead-GPU-driver black screen.
- `ntfsfix -n` all three → 0 dirty flags → `reboot`.

## Target OS note

User wants **Windows 10 IoT Enterprise LTSC (full, not eval)** for the eventual reinstall. Full LTSC is not on Microsoft's public eval center; genuine rebuild path = UUP dump from Microsoft update servers. Confirm full-vs-eval BEFORE downloading anything — user corrected this mid-session.

## Never do

- Wipe the lab NAS drive (4TB Seagate, `D:` / `NZ1NAS`) as install-media staging. Hard rule, saved in memory as well.
- Run the PXE server from a NAT'd WSL endpoint.
- Declare the PXE server 'up' from process-alive alone — check the UDP binds.

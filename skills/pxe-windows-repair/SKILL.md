---
name: pxe-windows-repair
description: Use when a PXE-capable PC won't boot Windows. Network repair
---

Repair or reinstall Windows on a LAN PC via PXE when it won't boot but its PXE ROM works.

## Architecture

- **Server** (any LAN Windows PC): DHCP-proxy + TFTP + HTTP via Tiny PXE Server (portable - github erwan2212/tinypxeserver)
- **Patient**: PXE ROM chains a loader, boots WinPE/Setup or Linux rescue from the network

## Server config (config.ini)

- `proxydhcp=1` MANDATORY when a router already does DHCP
- `filename=<loader>`: netboot.xyz.kpxe (menu) or ipxe-undionly.kpxe (custom chain)
- `altfilename=<script.ipxe>`: handed to iPXE on 2nd DHCP request - chain custom scripts here
- `[arch] 00007=<efi>` + `00009=<efi>` for UEFI; `start=1` autostarts
- Firewall: inbound UDP 69 + 4011, TCP http-port

## Windows install chain (iPXE + wimboot)

TFTP root: wimboot, bootmgr, BCD, boot.sdi, sources/boot.wim, sources/install.wim (~4GB - serve over HTTP)

```
#!ipxe
kernel http://<srv>:<port>/wimboot
initrd http://<srv>:<port>/win10/bootmgr bootmgr
initrd http://<srv>:<port>/win10/bcd_bios BCD
initrd http://<srv>:<port>/win10/boot.sdi boot.sdi
initrd http://<srv>:<port>/win10/boot.wim boot.wim
boot
```

Pitfalls: `pause` is NOT an iPXE command (dies 'Exec format error'); verify URLs return 200 first; inject into boot.wim via wimtools (chmod writable on /mnt/c first).

## WinPE takeover

- Shift+F10 = cmd console on any Setup screen
- WinPE 19041: NO WinRM/PowerShell. Remote = `net start lanmanserver` + `net share repair=C:\`, or FTP-push logs
- `net localgroup` fails in PE (1376); share without /grant works
- 'No device drivers' = missing Intel RST/VMD: inject INF+SYS+CAT into /Windows/Inf, /System32/drivers, /System32/CatRoot/{F750E6C3-38EE-11D1-85E5-00C04FC295EE}; F6 packs from winraid mirrors via megatools
- Browse sees drive, list empty = dirty table: diskpart > clean > convert gpt

## Linux rescue (fastest first move)

SystemRescue via netboot.xyz. On box: passwd, systemctl start sshd, **nft flush ruleset** (nft rules DROP inbound SSH even while sshd listens). Over SSH: smartctl, mount -o ro, ntfsfix -d, rsync off.

## Proven sequence

1. PXE SystemRescue, SSH in
2. SMART + mount read-only (readable = alive)
3. ntfsfix -d fixes $MFTMirr + clears journal (worked on real GPU-death corruption)
4. Delete hiberfil.sys (stops resume into dead-GPU black screen)
5. Still dead: CIFS-mount NAS, rsync C:\Users, reinstall

## Reality checks

- SMART can PASS on a dying controller: Linux mounts it, Windows 'i/o device error'. Trust behavior over SMART.
- PXE window can be seconds - force boot menu (F12/F11/F8) each retry
- Catch patient IP with raw-socket DHCP sniffer or nmap sweep loop
- WSL is NAT'd: sniff from Windows host side, routed scans from WSL

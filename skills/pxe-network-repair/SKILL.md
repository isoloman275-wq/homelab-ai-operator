---
name: pxe-network-repair
description: Boot a dead PC via PXE and repair Windows over the network
---

# PXE Network Repair

Repair a machine that won't boot Windows **without any USB install media**: stand up a PXE boot server on another LAN machine, netboot the patient into a Linux rescue environment over the network, then drive the repair remotely over SSH.

**WinPE/Setup-phase work** (driver injection into boot.wim, takeover attempts of a running Setup, disk-I/O diagnostics) has a validated-plus-failure-record addendum in `references/network-windows-install.md`. Net lessons: stock boot.wim supports NO remote takeover (no ssh/WinRM — Shift+F10 one-liners relayed by the user are the only channel); `diskpart clean` throwing I/O errors with clean SMART means a write-locked/dying drive, not a driver problem; 'Browse sees the disk but the list is empty' = driver is loaded, stop injecting drivers and test the disk.

## When to reach for this

- PC shows a PXE boot screen / Intel Boot Agent and Windows won't start.
- No spare USB stick (or no install ISO on hand).
- The machine still powers on and POSTs — this is a boot/filesystem problem, not dead hardware.

## Phase 0 — Triage before touching the network

A PXE screen often means Windows already failed and boot fell through to the NIC. Common traps:

- **Parked in the NIC's own setup menu** = the client transmits NOTHING. If the wire is silent, ask the user to exit the menu (Esc → Exit Saving Changes) so PXE actually attempts and broadcasts.
- **Blank screen AFTER Automatic Repair finishes** with a recently-died GPU = the OS boots but blacks out when the GPU driver loads (BIOS/WinRE use basic display). Not disk death. Fix = remove the stale `hiberfil.sys` (fast-startup resume re-injects the dead driver state) and reinstall the GPU driver.
- **BIOS detecting the SSD** means the disk is electrically alive; corruption at this stage is usually filesystem-level (repairable), not physical.
- Confirm disk health early: SMART `Reallocated_Sector_Ct` / `Reported_Uncorrect` raw values — if 0, repair-in-place; if climbing, replace before reinstalling anything.

## Phase 1 — See the patient on the wire

A PXE client that never gets a lease has no IP — ARP sweeps and port scans can't see it. Two layers:

1. **DHCP sweep watcher** (catches the client once it leases): loop `nmap -sn <subnet>` every 6-12s, diff against a baseline file, log new hosts.
2. **Raw-socket DHCP sniffer** (sees the DISCOVER itself, pre-lease): AF_PACKET socket filtering UDP src/dst port 67/68; DHCP magic cookie `63825363` at payload offset 236, client MAC at payload offset 28.

Expect flapping: a PXE client boot-looping appears/disappears between sweeps. Log repeated new-host hits, don't dedupe them away.

## Phase 2 — PXE server (proxyDHCP mode)

Use **Tiny PXE Server** (portable, single exe, DHCP+TFTP+HTTP in one) + **netboot.xyz** boot images (1MB, gives a full distro menu over the internet).

- Server download: GitHub `erwan2212/tinypxeserver` → `pxesrv.zip` (raw link). Mirror lists rot — search before guessing URLs.
- Boot images: `https://boot.netboot.xyz/ipxe/netboot.xyz.kpxe` (BIOS) and `netboot.xyz.efi` (UEFI). NOTE: the often-quoted `undionly.kpxe` path 404s — `netboot.xyz.kpxe` is the working name.
- If the LAN router already runs DHCP, set `proxydhcp=1` in config.ini — Tiny PXE answers ONLY PXE clients and must not fight the router for leases.
- Set `start=1` so the daemons auto-online on launch (otherwise the exe sits idle waiting for a GUI button press — verify UDP 4011/69 are actually BOUND before declaring the server up).
- `[arch]` overrides: `00007=<efi image>` (x64 UEFI), `00009=<efi image>` (aarch64 UEFI); `filename=` covers BIOS clients.
- Open firewall: UDP 69 (TFTP) + UDP 4011 (proxyDHCP) + the HTTP port, inbound, before testing.
- Keep boot images in the TFTP root (`files/` dir next to the exe).

## Phase 3 — Rescue environment + remote drive

The relay-typing-commands-through-the-user loop is slow and error-prone. Get SSH up on the patient ASAP so the agent drives:

1. From netboot.xyz: **Live CDs / Tools → SystemRescue** (SystemRescue CD; ships ntfsfix, smartctl, ntfs-3g, sshd).
2. On the patient console: `passwd` (set a root password) → `systemctl start sshd`.
3. **GOTCHA — firewall:** SystemRescue ships an nftables ruleset that DROPS inbound SSH even when sshd listens on `0.0.0.0:22`. Symptom: `ss -tlnp` shows `0.0.0.0:22` on the patient, but outside connections time out as `filtered` while ping answers. Fix on the patient: `nft flush ruleset`. Then connect with sshpass and take the wheel.
4. SystemRescue's SSH service is `sshd` (`systemctl status sshd` to confirm active).

## Phase 4 — The Windows repair sequence

Standard in-place repair (all verified working end-to-end):

1. Identify layout: `lsblk` (Windows disks = `sda1` ~50-100MB System Reserved, `sda2` big C:, `sda3` ~500MB WinRE).
2. SMART: `smartctl -H -A /dev/sda`.
3. Read-only probe first: `mount -o ro /dev/sda2 /mnt/win` — if `Windows`, `Users`, `Program Files` list fine, metadata is intact.
4. Repair: `ntfsfix -d /dev/sda2` (fixes $MFTMirr mismatch, empties $LogFile, clears dirty flag). Expect a harmless `Failed to sync device` warning mid-run; judge by the final `processed successfully` + a successful read-write test (`touch` a file, delete it).
5. Repeat `ntfsfix` on the other Windows partitions.
6. `sda1` "System Reserved" is **NTFS, not FAT/EFI** — a vfat mount failing there is expected, not an error. Verify with `file -s /dev/sda1` (should say `NTFS ... contains bootstrap BOOTMGR`).
7. Delete stale `hiberfil.sys` from C: (fast-startup resume of a crashed-driver session causes boot black screens — deleting it only disables fast startup, no data loss).
8. Final check: `ntfsfix -n` (no-op dry run) on every partition → zero dirty flags → `reboot`.

## Phase 5 — Full Windows reinstall over PXE (no USB)

When repair-in-place fails (e.g. boots to black screen even after clean NTFS) and the user OKs a reinstall, the same PXE server can boot Windows Setup itself — validated end-to-end:

1. **Source the ISO**: full (non-eval) LTSC/IoT editions are mirror-only; verify SHA-256 against the published hash before use.
2. **Stage files** into Tiny PXE's TFTP root (`files/win10/`): `bootmgr` (ISO root), `bcd_bios` (ISO `/boot/bcd`), `boot.sdi` (`/boot/`), `boot.wim` + `install.wim` (`/sources/`). `wimboot` ships inside pxesrv.zip's `files/` — no separate download.
3. **Chain script** `files/win10.ipxe` (see reference file for exact content): `#!ipxe` + `kernel wimboot` + `initrd` lines for the four files, fetched over HTTP (`http://<server-ip>:8088/win10/...` — faster and more reliable than TFTP for the 600MB boot.wim).
4. **Config**: `filename=ipxe-undionly.kpxe` (stage-1 iPXE, also shipped in `files/`) and `altfilename=win10.ipxe` — the PXE ROM gets iPXE, iPXE re-DHCPs, and the altfilename hands it the install script. Tiny PXE's HTTPd serves the TFTP root; verify with a curl of one staged file (expect 200) before rebooting the patient.
5. Restart pxesrv after any config.ini edit — edits don't hot-reload.
6. **Keep-files installs**: if the user wants data preserved, back up `C:\Users` over the patient's SSH link to a NAS/other box BEFORE rebooting into Setup; Setup's Custom install then formats C: cleanly.
7. SystemRescue SSH sessions die on console screen-blank/powersave — if the patient goes quiet mid-job, wake the console and re-run `nft flush ruleset` to reopen SSH.

## Lessons

- Verify every daemon with a socket-bind check, not process-alive: a GUI-mode PXE server shows a healthy process while serving nothing.
- `filtered` + ping-OK from outside almost always = firewall on the TARGET, not the network path.
- Windows repair ISO choice: full LTSC/IoT editions are NOT on Microsoft's public eval page; they can be rebuilt from genuine Microsoft update servers via UUP dump when a real reinstall is needed. Eval ISOs carry a watermark and are a different SKU — confirm which the user wants before downloading.
- Server-side downloads: a failing download URL is usually a dead mirror, not a dead tool — web-search the project's canonical repo before declaring the tool unavailable.
- UUP dump does NOT carry IoT/Enterprise LTSC editions (retail 19044 builds expose only Core/Pro; `enterpriseS`/`IoTEnterpriseS` = `UNSUPPORTED_COMBINATION`), and Microsoft's LTSC fwlink redirects to the EVAL ISO. The full IoT Enterprise LTSC ISO is mirror-only — ALWAYS verify the downloaded ISO's SHA-256 against the published hash before installing from it.
- PowerShell `Invoke-WebRequest -Method Head` probes fail on some mirrors (403 without a browser UA) where `curl -sIL -A "Mozilla/5.0"` succeeds — verify a mirror with curl before writing it off.

Worked example with concrete hosts/paths/IPs: `references/worked-example-windows-repair.md`. Network Windows-install (Phase 5) recipe: `references/network-windows-install.md`.
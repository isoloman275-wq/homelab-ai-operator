# Network Windows Install (PXE, no USB) — validated recipe

Companion to SKILL.md Phase 5. Core chain validated live end-to-end. Session-2
addendum at the bottom covers WinPE driver injection and remote takeover of a
running Setup — partially validated, failure modes recorded.

## 1. Source the ISO (full LTSC/IoT, non-eval)

Dead ends (verified):
- Microsoft eval fwlinks (`go.microsoft.com/fwlink/p/?LinkID=2195404...`) → redirect to `CLIENT_LTSC_EVAL_...iso` (eval SKU, 90-day, user rejected).
- UUP dump API: retail 19044 builds expose only `CORE/PROFESSIONAL/COREN/PROFESSIONALN/PPIPRO`. `edition=enterpriseS|IoTEnterpriseS|iotenterprise` → `UNSUPPORTED_COMBINATION`. UUP also rate-limits aggressively (sleep 45-90s between calls).

Working path: public mirrors of the genuine DVD image. Verify by SHA-256 against the published hash, e.g.:
- `en-us_windows_10_iot_enterprise_ltsc_2021_x64_dvd_257ad90f.iso` = `a0334f31ea7a3e6932b9ad7206608248f0bd40698bfb8fc65f14fc5e4976c160`

Mirror probe gotchas: BobPony returns 403 (UA-blocked); `computernewb.com/isos/windows/` works via `curl -sIL -A "Mozilla/5.0"` but Invoke-WebRequest HEAD throws. Download with `curl -sL -A "Mozilla/5.0" -o out.iso <url>` in the background, then `sha256sum` before anything else.

## 2. Stage the PXE tree (Tiny PXE Server)

Mount the ISO and copy into Tiny PXE's TFTP root (`files/` next to pxesrv.exe):

```
files/win10/bootmgr     <- ISO root /bootmgr
files/win10/bcd_bios    <- ISO /boot/bcd
files/win10/boot.sdi    <- ISO /boot/boot.sdi
files/win10/boot.wim    <- ISO /sources/boot.wim (~600MB, the WinPE that Setup runs in)
files/win10/install.wim <- ISO /sources/install.wim (~4GB, the actual Windows image)
```

`wimboot`, `ipxe-undionly.kpxe`, `ipxe-snponly-x86-64.efi` all ship inside pxesrv.zip's `files/` — do not download them separately.

## 3. Chain script — `files/win10.ipxe`

HTTP beats TFTP for the big files; Tiny PXE's HTTPd (config `[web] port=8088`) serves the TFTP root:

```
#!ipxe
echo Homelab AI Operator Windows 10 IoT LTSC 2021 network installer
kernel wimboot
initrd win10/bootmgr    bootmgr
initrd win10/bcd_bios   BCD
initrd win10/boot.sdi   boot.sdi
initrd win10/boot.wim   boot.wim
boot
```

(TFTP paths shown; prefix each with `http://<server-ip>:8088/` for HTTP fetch. WinPE's Setup finds install.wim via network share/drive mapping later — the wimboot initrds only need boot.wim.)

**iPXE script gotcha:** `pause` is NOT an iPXE command — a script containing it
aborts at that line with `command not found`, then iPXE tries to execute the
next-initrd'd file (boot.wim) directly → `Exec format error (2e0220011)`. Keep
the script to kernel/initrd/boot only; no interactive commands.

## 4. config.ini (Tiny PXE)

```
filename=ipxe-undionly.kpxe   ; stage-1: PXE ROM downloads iPXE
altfilename=win10.ipxe        ; stage-2: iPXE re-DHCPs and is handed this script
proxydhcp=1                   ; router already runs DHCP
start=1                       ; auto-online daemons on launch
[web] port=8088
```

Restart pxesrv.exe after ANY config.ini edit (no hot-reload). Verify before rebooting the patient:
- UDP 69 + 4011 bound: `Get-NetUDPEndpoint | ? LocalPort -in 69,4011`
- HTTP serving: `curl -s -o /dev/null -w '%{http_code}' http://<server-ip>:8088/win10/bootmgr` → 200

## 5. Boot the patient

Reboot → PXE ROM → iPXE (DHCP) → win10.ipxe → wimboot loads bootmgr/BCD/boot.sdi/boot.wim → Windows Setup (WinPE) on screen.

In Setup: Custom install → format C: only after user data was backed up (e.g. rsync C:\Users over the patient's SystemRescue SSH link to a NAS BEFORE rebooting into Setup).

## Session gotchas

- SystemRescue SSH dies when the patient's console blanks (powersave) — wake the console, re-run `nft flush ruleset`, reconnect.
- Some SystemRescue builds lack tcpdump; use a raw AF_PACKET DHCP sniffer (see SKILL.md Phase 1) instead.
- Verify the PXE server actually SERVES (socket bound + curl test), not just that the process is alive — the GUI exe idles without `start=1`.

---

# SESSION-2 ADDENDUM: WinPE driver injection + Setup takeover (partially validated)

Second session hit 'Select the drivers to install — no device drivers were
found' (WinPE can't see the NVMe/SATA controller, typically Intel VMD/RST).
What follows records what WORKED, what DIDN'T, and the failure modes observed.

## Sourcing the F6 driver (Intel discontinued the easy path)

- Intel now ships only `SetupRST.exe` (their CDN 403s plain downloads anyway);
  the classic `f6flpy-x64-*.zip` packages are discontinued.
- Working source: Win-Raid forum (winraid.level1techs.com) thread 'Intel RST/RSTe
  Drivers' hosts MEGA links to the extracted F6 packs. Fetch with `megatools
  get <mega-url>` (apt install megatools), then extract with `unrar-free x`.
- Genuine VMD F6 pack = `iaStorVD.inf` (UTF-16), `iaStorVD.sys`, `iaStorVD.cat`,
  `RstMwService.exe`, `RstMwEventLogMsg.dll`. v19.5.8.1059 covers Win10 11th-gen
  VMD; v20.2.13.1038 covers 12th-15th gen. Match the pack to the patient's CPU
  generation before injecting.

## Injecting into boot.wim (wimtools, verified working)

```
sudo apt install wimtools
wimlib-imagex info boot.wim            # index 1 = WinPE env, index 2 = Setup
sudo chmod 666 boot.wim                # else update fails 'Permission denied'
printf 'add /path/iaStorVD.inf /Windows/Inf/iaStorVD.inf\nadd /path/iaStorVD.sys /Windows/System32/drivers/iaStorVD.sys\nadd /path/iaStorVD.cat /Windows/System32/CatRoot/{F750E6C3-38EE-11D1-85E5-00C04FC295EE}/iaStorVD.cat\n' > /tmp/wimcmds.txt
sudo wimlib-imagex update boot.wim 2 < /tmp/wimcmds.txt
wimlib-imagex dir boot.wim 2 | grep iaStor   # verify
```
- wimlib heredocs/inline `$VAR`s don't expand — write the command list to a
  real file first (printf) and pipe the file in.
- `--shutdown` is not a valid option to `update add` (errors out).
- Keep a pre-edit `boot_wim_backup.wim` copy.

Injection verified (files present in WIM), BUT Setup still showed no disks —
**files-in-place ≠ driver active**. Proper activation needs DISM /Add-Driver or
an unattended answer file; file-drop alone did not load it. Not resolved.

## Observing a WinPE patient

- WinPE boots are transient on the wire: DHCP at boot, IP may drop later.
- **ARP 'Stale'/'Incomplete' state on the Windows host = the box is NOT answering,
  regardless of the entry existing.** Only 'Reachable'/'Probe' states are live.
- Raw-socket sniffers can be run on the Windows host itself (`SIO_RCVALL` on
  IPPROTO_IP, bind the LAN IP) — sees DHCP/PXE bursts a WSL guest cannot. Launch
  via elevated PowerShell; note stdout is UTF-16 and output buffering lags.
- A WinPE patient with IP but nothing listening on 445/21/80: the injected
  startnet either didn't run or its `net start` calls failed silently.

## Attempting remote takeover of a running Setup (failure record)

Goal: drive the stuck Setup from the agent instead of relaying keystrokes.

- WinPE has NO sshd, NO WinRM (feature absent from stock boot.wim), no PowerShell
  remoting. Verified by grepping the WIM file listing.
- `startnet.cmd` DOES run on WinPE boot (index 1, /Windows/System32/startnet.cmd —
  extract, edit, re-inject with wimlib `update`). Adding `net user admin … /add`,
  `net localgroup administrators …` → **error 1376** (no SAM DB in PE — localgroup
  manipulation is unreliable in WinPE). `net start lanmanserver` + `net share
  repair=C:\` typed MANUALLY at Shift+F10 DID succeed both times reported.
- BUT even with the share created, from outside: error 67/53, TCP 445 closed.
  The PE Server service either didn't bind or PE's stack blocks inbound.
  SMB takeover of WinPE: NOT achieved.
- `ftp -s:\IntelRST\report.txt` outbound from PE to an agent-side pyftpdlib
  server (custom auth, port 2121, `perm='elradfmwMT'`) is the better channel —
  pyftpdlib's CLI module rejects `-w <password>`; write a small server script.
  Not confirmed received before session end.
- **NET LESSON: WinPE takeover over SSH/WMI is not practically achievable with
  stock boot.wim.** The reliable remote channel is the Shift+F10 console with the
  user relaying single one-liners (`&`-chained). Keep those to ONE line: PE cmd
  handles `cmd1 & cmd2 & cmd3` fine, but multi-step stories across turns fail.

## The disk that drove this: I/O device error

`diskpart → select disk 0 → clean` returned **'I/O device error'** on a drive
whose SMART was PASSED with zero reallocated sectors. SMART passing does NOT
mean the drive accepts writes — SSDs can lock read-only after a power event
while SMART looks perfect. When `clean` throws I/O errors in Setup:
- suspect the drive (write-protect latch / controller damage) even with clean SMART;
- test on another machine before condemning, but plan the replacement;
- do NOT burn hours on driver reloads — the driver question is already answered
  by Browse seeing the disk (see below).

Key diagnostic distinction (verified this session): **'Browse' on the Load-Driver
dialog seeing the disk while the disk list is empty** means the storage DRIVER
is loaded and the problem is the disk/partition state — NOT a missing driver.
Don't inject more drivers at that point; test the disk.

## WinPE boot-loop on 'Diagnosing your PC'

After a failed Setup attempt, the patient boot-loops into WinRE ('Diagnosing
your PC') — boot order flipped back to disk. Fix: full power-off (hold 5s),
then one-shot boot menu (F12) → explicit network entry. Do not rely on default
boot order after a failed install.

# Delivering the built app onto AUX-NODE (target box) — 2026-08-05

Context: Project 6 "Kaitiaki Tamariki" after-school tutor is built to run on AUX-NODE
(Windows 10 IoT LTSC, the kids/gaming PC). This note records how to get a local-LLM
conversational app onto a target box that has no open remote-admin channel.

## AUX-NODE reachability reality (verified 2026-08-05)
- Pingable, SMB :445 open, but SSH(22)/WinRM(5985/5986)/RDP(3389) all CLOSED.
- Blank-password SMB admin (`C$`/`admin$`) is blocked by Windows policy:
  "Account restrictions are preventing this user from signing in... blank passwords
  aren't allowed."
- So you CANNOT scp/push the built app onto AUX-NODE from MAIN-NODE directly.

## Reliable delivery pattern
1. Build the app SELF-CONTAINED: pure Python stdlib backend + one static HTML = no
   external deps, nothing to install on AUX-NODE beyond Python. (The tutor backend uses only
   `http.server` + `urllib`; the UI is a single `index.html`.)
2. Zip the whole app dir and stage at a Windows-visible path:
   `C:\Users\Admin\Downloads\<name>_app.zip` (WSL: `/mnt/c/Users/Admin/Downloads/...`).
   Give the user the Windows path so they can hop it to AUX-NODE (USB, reachable share, etc.).
3. Enable the documented scp path (`user@aux-node`) with a ONE-TIME console step
   on AUX-NODE (paste in an elevated PowerShell):
   - `Add-WindowsCapability -Online -Name "OpenSSH.Server~~~~0.0.1.0"`
   - `Set-Service sshd -StartupType Automatic; Start-Service sshd`
   - Authorize MAIN-NODE's public key (no password): write it (no newline) to
     `$env:ProgramData\ssh\administrators_authorized_keys`, then
     `icacls ... /inheritance:r`, grant SYSTEM:F and Administrators:F.
   - Confirm `netstat -ano | findstr :22` shows LISTENING.
4. Once sshd is up, `scp` the zip across with key auth (no password prompt).
   Run on AUX-NODE: `python <backend>.py --port 8123`, browse `http://localhost:8123`
   (LAN: `http://<m3-ip>:8123`).

## "Username is Admin, no password"
When the user gives a passwordless Windows admin account, do NOT try a blank-password
SMB login — Windows blocks it for remote admin. Authorize the MAIN-NODE public key in
`administrators_authorized_keys` (the admin key file, NOT `authorized_keys`) and use
key-based ssh. Windows OpenSSH only reads the `administrators_authorized_keys` file for
Users in the Administrators group, and requires its ACL to be SYSTEM+Administrators only.

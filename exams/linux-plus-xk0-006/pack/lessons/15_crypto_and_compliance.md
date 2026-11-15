# Module 15 — Cryptography, certificates, and compliance

> **Exam objectives:** Linux+ 3.5 (given a scenario, implement cryptography)
> and 3.6 (given a scenario, implement compliance and auditing).
> **Study time:** about 120 minutes, including the mission.
> **Mission:** `build_pki.sh` plus `crypto_audit.py` — build a real root CA and
> server certificate, hash and HMAC artifacts, shred a secret, and audit the
> result.

## What the exam expects

### Cryptography (3.5)

- symmetric encryption: AES, `openssl enc`, key management,
- asymmetric encryption: RSA, ECDSA, Ed25519, key exchange,
- hashing: SHA-256, SHA-512, `sha256sum`, `md5sum` (legacy),
- HMAC and digital signatures,
- GPG for file and email encryption/signing,
- TLS: certificates, CSRs, CAs, chains, trust stores, `openssl s_client`,
- disk encryption: LUKS2, `cryptsetup`,
- VPN: WireGuard, IPsec,
- secure destruction: `shred`, `wipe`, `dd`, crypto-erase,
- steganography (concept only).

### Compliance and auditing (3.6)

- standards: PCI-DSS, HIPAA, GDPR, SOX, CIS benchmarks, STIG,
- vulnerability management and CVE/CVSS scoring,
- patching cadence,
- file integrity monitoring: AIDE, Tripwire, `rpm -Va`, `debsums`,
- rootkit detection: `rkhunter`, `chkrootkit`,
- evidence, retention, and audit trails,
- banners and legal notices,
- license and open-source compliance.

## Symmetric encryption

One key encrypts and decrypts. Fast, used for bulk data.

```bash
openssl enc -aes-256-cbc -pbkdf2 -salt -in data.tar -out data.tar.enc
openssl enc -d -aes-256-cbc -pbkdf2 -in data.tar.enc -out data.tar
```

`-pbkdf2` derives the key from a passphrase properly. Without a modern KDF,
old examples are weak. For real data, prefer LUKS or age/GPG over
`openssl enc` with a shared passphrase.

Algorithms to know:

| Algorithm | Type | Notes |
|---|---|---|
| AES-256-GCM | symmetric AEAD | authenticated, the default for TLS and disk | 
| ChaCha20-Poly1305 | symmetric AEAD | fast without AES hardware |
| RSA-2048/3072/4096 | asymmetric | widely compatible, slower |
| ECDSA P-256/P-384 | asymmetric | smaller keys, fast |
| Ed25519 | asymmetric signature | modern default for SSH/GPG |
| X25519 | key exchange | WireGuard, TLS ECDHE |
| SHA-256/SHA-512 | hash | integrity, signatures |
| MD5/SHA-1 | hash | broken for security use |

## Hashing and HMAC

A hash is a fixed-size fingerprint. It detects accidental and malicious
changes but is not encryption.

```bash
sha256sum file
sha512sum file
md5sum file          # legacy, collision-prone
sha256sum -c manifest.sha256
find . -type f -print0 | xargs -0 sha256sum > manifest.sha256
```

An **HMAC** is a hash keyed with a secret. It proves both integrity and
authenticity between parties that share the key:

```bash
openssl dgst -sha256 -hmac "shared-key" -out file.hmac file
openssl dgst -sha256 -hmac "shared-key" -verify file.hmac file
```

A plain hash cannot stop an attacker who can rewrite both the file and the
manifest. An HMAC can, as long as the key stays secret. A **digital signature**
does the same with a private key and is verifiable by anyone with the public
key.

## GPG

GPG implements OpenPGP: keys, signatures, and encryption.

```bash
gpg --full-generate-key
gpg --list-keys
gpg --list-secret-keys
gpg --export -a alice@example.com > alice.asc
gpg --import alice.asc
gpg --sign file
gpg --verify file.gpg
gpg --encrypt --recipient alice@example.com file
gpg --decrypt file.gpg
gpg --detach-sign --armor file
gpg --verify file.asc file
```

- **sign** proves origin and integrity,
- **encrypt** provides confidentiality to the holder of the private key,
- **sign + encrypt** gives both,
- a key server or internal keyserver distributes public keys,
- always verify a fingerprint out of band before trusting a key.

GPG is also how package repositories publish signed metadata; `apt` and `dnf`
verify those signatures (module 10).

## TLS and certificates

TLS protects data in transit. The pieces:

- **private key** — never leaves the server, mode 600,
- **CSR** — certificate signing request containing the public key and subject,
- **certificate** — the CA's signed statement binding a public key to names,
- **CA** — the authority that signs certificates,
- **chain** — leaf → intermediate(s) → root,
- **trust store** — the set of roots a client trusts,
- **SAN** — subject alternative names; modern clients ignore the old CN.

```bash
# Root CA
openssl genrsa -out pki/ca.key 2048
openssl req -x509 -new -nodes -key pki/ca.key -sha256 -days 3650 \
  -subj "/CN=Lab Root CA" -out pki/ca.crt

# Server key, CSR, and certificate
openssl genrsa -out pki/server.key 2048
openssl req -new -key pki/server.key -subj "/CN=app.internal" \
  -out pki/server.csr
openssl x509 -req -in pki/server.csr -CA pki/ca.crt -CAkey pki/ca.key \
  -CAcreateserial -days 365 -sha256 \
  -extfile <(printf 'subjectAltName=DNS:app.internal,DNS:localhost\n') \
  -out pki/server.crt

chmod 600 pki/ca.key pki/server.key
```

Inspect and verify:

```bash
openssl x509 -in pki/server.crt -noout -subject -issuer -dates -ext subjectAltName
openssl verify -CAfile pki/ca.crt pki/server.crt
openssl x509 -in pki/server.crt -noout -checkend 2592000   # 30 days left?
openssl x509 -in pki/server.crt -noout -text | grep -A1 'Subject Alternative'
```

### A live TLS check

```bash
openssl s_client -connect app.internal:443 -servername app.internal -showcerts
openssl s_client -connect app.internal:443 -tls1_2
echo | openssl s_client -connect app.internal:443 2>/dev/null | \
  openssl x509 -noout -dates -subject -issuer
```

The handshake prints `Protocol:`, `Cipher:`, the certificate chain, and
verification result. A self-signed certificate on a public service is a
finding; a TLS 1.0/1.1 handshake is a finding; a NULL or RC4 cipher is a
finding.

### Hardening TLS

```ini
# /etc/ssl/openssl-hardening.cnf
[system_default_sect]
MinProtocol = TLSv1.2
CipherString = HIGH:!aNULL:!MD5
```

`MinProtocol = TLSv1.2` (or 1.3 where supported) removes obsolete versions.
`HIGH:!aNULL:!MD5` keeps strong ciphers and removes anonymous and MD5-based
suites. Modern servers should prefer TLS 1.3, forward secrecy (ECDHE), and
automated certificate renewal.

### Trust stores

```bash
ls /etc/ssl/certs
sudo cp lab-ca.crt /usr/local/share/ca-certificates/
sudo update-ca-certificates          # Debian
sudo cp lab-ca.crt /etc/pki/ca-trust/source/anchors/
sudo update-ca-trust                 # RHEL
```

A private CA works only if every client trusts it. For a public service, use a
public CA; never install a self-signed leaf certificate and call it done.

## LUKS2 disk encryption

```bash
sudo cryptsetup luksFormat --type luks2 /dev/sdb
sudo cryptsetup luksOpen /dev/sdb cryptdata
sudo mkfs.ext4 /dev/mapper/cryptdata
sudo mount /dev/mapper/cryptdata /mnt/data
sudo cryptsetup luksClose cryptdata
sudo cryptsetup luksDump /dev/sdb
sudo cryptsetup luksAddKey /dev/sdb
```

`/etc/crypttab` and `/etc/fstab` make it persistent. LUKS protects data at
rest when the machine is off; it does not protect a running system. For
servers, combine it with a TPM or a network-bound unlock (Clevis/Tang) and
understand the trade-off.

## VPNs

- **WireGuard** — modern, small, fast. Peers exchange public keys; the
  configuration is a few lines. `wg show` displays handshakes and transfer.
- **IPsec** — standards-based, used for site-to-site and with strongSwan or
  Libreswan. More complex but widely interoperable.

```bash
wg genkey | tee private.key | wg pubkey > public.key
wg show
ip link show wg0
```

VPNs protect traffic in transit between networks. They do not replace
authentication, authorization, or endpoint hardening.

## Secure destruction

Deleting a file removes its name, not its blocks. Depending on the medium:

```bash
shred -u -n 3 secrets/old-token.txt
shred -vfz -n 3 /dev/sdb
dd if=/dev/urandom of=/dev/sdb bs=1M status=progress
```

- `shred` overwrites the file's blocks and unlinks it; it is unreliable on
  journaling filesystems, copy-on-write filesystems, SSDs with wear levelling,
  and snapshots.
- For **SSDs**, use the drive's secure erase (`hdparm --security-erase`,
  `nvme format`) or full-disk encryption plus crypto-erase (destroy the key).
- For **cloud volumes**, rely on provider guarantees or encryption plus key
  destruction.
- For **backups and archives**, you must destroy every copy.

`wipe` is an alternative; `srm` exists on some systems. Document the method and
verify it for the media in use.

## File integrity monitoring

**AIDE** builds a database of hashes, permissions, and metadata, then reports
changes:

```bash
sudo aide --init
sudo mv /var/lib/aide/aide.db.new.gz /var/lib/aide/aide.db.gz
sudo aide --check
```

Package-level checks:

```bash
sudo rpm -Va                 # verify RPM payloads
sudo debsums -c              # Debian packages
```

Rootkit detection:

```bash
sudo rkhunter --check --sk
sudo chkrootkit
```

These tools have false positives; the value is a baseline plus a review
process. A daily AIDE report to a central log is a real control; an unread one
is not.

## Vulnerability management

- **CVE** — a public identifier for a vulnerability.
- **CVSS** — a 0–10 severity score; 9.0+ is critical.
- **Advisory** — vendor statement with affected versions and a fix.
- **Patch cadence** — how quickly you apply fixes; critical vulnerabilities
  usually need days, not months.
- **Exposure** — a critical CVE on an unreachable service is less urgent than a
  medium one on the internet-facing edge. Prioritize by exploitability and
  reachability.
- **SBOM** — software bill of materials; know what is inside your images and
  packages.

```bash
sudo dnf updateinfo list security
sudo dnf update --security
sudo apt list --upgradable
sudo unattended-upgrade --dry-run
```

## Compliance

Compliance is evidence, not intention. For each control, keep:

- the **policy** (what must be true),
- the **configuration** (what is true now),
- the **evidence** (logs, reports, screenshots, hashes),
- the **review cadence** (who checks, how often),
- the **exception** process (documented risk acceptance).

Common frameworks:

| Framework | Focus |
|---|---|
| CIS Benchmarks | concrete hardening settings per platform |
| DISA STIG | US DoD hardening requirements |
| PCI-DSS | payment card data |
| HIPAA | health data (US) |
| GDPR | personal data (EU) |
| SOX | financial reporting controls |

Banners (`/etc/issue`, `/etc/issue.net`, `/etc/motd`) are a small but
frequently tested control: they warn that access is monitored and unauthorized
use is prohibited. `issue` is shown locally, `issue.net` to remote users before
login (via `Banner` in `sshd_config`), and `motd` after login.

## Mission 15 — what you build

1. **`build_pki.sh`** (executable, `set -euo pipefail`) that:
   - creates a 2048-bit RSA root CA (`pki/ca.crt`, `pki/ca.key`) with subject
     `CN=Lab Root CA`,
   - creates a server key/CSR for `CN=app.internal`,
   - signs the server certificate with the CA, adding
     `subjectAltName=DNS:app.internal,DNS:localhost`,
   - sets both private keys to mode 600,
   - writes `pki/manifest.sha256` with SHA-256 for both certificates,
   - writes `pki/server.hmac` using
     `openssl dgst -sha256 -hmac "lab-key"`,
   - destroys `secrets/old-token.txt` with `shred -u`,
   - writes `etc/ssl/openssl-hardening.cnf` with `MinProtocol = TLSv1.2` and
     `CipherString = HIGH:!aNULL:!MD5`,
   - writes an “Authorized use only.” banner to `etc/issue`, `etc/issue.net`,
     and `etc/motd`,
   - writes `compliance/audit.md` recording the evidence.

2. **`crypto_audit.py --root .`** printing JSON with `ca_subject`, `ca_is_ca`,
   `server_subject`, `server_issuer`, `server_san`, `server_days_remaining`,
   `key_modes`, `manifest_valid`, `hmac_valid`, `tls_min_protocol`,
   `weak_algorithms`, `banners`, `banner_ok`, `expired_secret_present`.

The CA is self-signed by design; the **server** certificate must be signed by
the CA. In production, use a trusted commercial or organizational root and
never a self-signed leaf certificate on a public service. Run
`python3 main.py verify 15`.

## Exam traps

- Hashing is not encryption; a hash cannot be reversed.
- A plain hash without a signature or HMAC does not prove authenticity.
- `md5sum` and SHA-1 are not acceptable for security decisions.
- A certificate without a matching SAN fails modern clients even if the CN is
  right.
- `openssl verify` needs the correct CA chain; a missing intermediate looks
  like a bad certificate.
- `shred` is not reliable on SSDs, CoW filesystems, or snapshots.
- LUKS protects data at rest only.
- A self-signed certificate is trust-on-first-use, not public trust.
- AIDE without a baseline is just a slow hash job.
- Patching without restarting the service does not apply the fix.

## Check yourself

1. What is the difference between a hash, an HMAC, and a signature?
2. Which fields make a certificate valid for `app.internal`?
3. What does `MinProtocol = TLSv1.2` change, and why?
4. How do you verify that a server certificate is signed by your CA?
5. Why can `shred` fail to destroy data on an SSD?
6. What does `rpm -Va` detect, and what does it miss?
7. Which commands show pending security updates on each distribution family?
8. What is the difference between `/etc/issue`, `/etc/issue.net`, and
   `/etc/motd`?

## Going deeper

- Build a two-tier CA (root + intermediate) and a full chain, then verify a
  leaf against it.
- Encrypt a file with GPG, sign it, tamper with it, and observe verification
  failing.
- Set up WireGuard between two VMs and confirm the handshake with `wg show`.
- Create a LUKS2 volume with a key file and a passphrase, then test both.
- Run AIDE before and after a deliberate change and read the report.

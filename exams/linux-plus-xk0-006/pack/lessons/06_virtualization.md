# Module 6 — Virtualization with QEMU, KVM, and libvirt

> **Exam objective:** Linux+ 1.7 — Summarize virtualization on Linux systems.
> **Study time:** about 90 minutes, including the mission.
> **Mission:** `vm_audit.py` — audit libvirt domain XML and snapshot inventory
> against a small policy.

## What the exam expects

Virtualization appears in both 1.7 and the troubleshooting domains. You need to
explain and use:

- **QEMU** (emulator and device model) and **KVM** (kernel acceleration),
- **libvirt**, **virsh**, and **virt-manager** as the management layer,
- **VirtIO** paravirtualized drivers and why they beat emulated hardware,
- disk image operations: create, convert, resize, inspect,
- VM states, resources (CPU, RAM, storage, network), templates, clones,
  migrations, and snapshots,
- network types: bridged, NAT, host-only/isolated, routed, open,
- bare metal versus virtual machines, and nested virtualization.

The exam uses “virtual machine tools — libvirt, virsh, virt-manager”. Know the
small set of `virsh` commands that covers daily work.

## The stack

```
physical host
  ├── KVM        kernel module (/dev/kvm) — hardware-assisted CPU virtualization
  ├── QEMU       device emulation, disk formats, networking backends
  ├── libvirt    daemon (libvirtd/virtqemud) — API, XML definitions, lifecycle
  └── virsh / virt-manager / OpenStack / oVirt — clients
```

- **KVM** requires CPU virtualization extensions (`vmx` on Intel, `svm` on AMD)
  exposed by the host firmware. Check with `lscpu | grep Virtualization` and
  `ls -l /dev/kvm`.
- **QEMU** can run without KVM (software emulation, much slower) and can
  emulate non-native architectures.
- **libvirt** stores domain XML under `/etc/libvirt/qemu/` and runtime state
  under `/var/lib/libvirt/` (images usually in `/var/lib/libvirt/images/`).

```bash
systemctl status libvirtd
virsh list --all
virsh uri
virt-host-validate
```

## Creating and controlling a VM with virsh

A minimal lifecycle:

```bash
# Define a VM from XML (no boot yet)
virsh define web01.xml

# Or install interactively (virt-install from virt-install package)
virt-install --name web01 --memory 4096 --vcpus 4 \
  --disk path=/var/lib/libvirt/images/web01.qcow2,size=40,bus=virtio \
  --network bridge=br0,model=virtio \
  --cdrom /var/lib/libvirt/images/almalinux.iso \
  --graphics none --console pty

virsh start web01
virsh shutdown web01        # graceful ACPI request
virsh destroy web01         # hard power off
virsh reboot web01
virsh suspend web01
virsh resume web01
virsh undefine web01 --remove-all-storage
```

State names in `virsh list --all`: `running`, `shut off`, `paused`,
`crashed`, `pmsuspended`. The file `vms/*.xml` is the persistent definition;
runtime changes made with `virsh` may be lost on restart unless you pass
`--config`.

```bash
virsh dominfo web01
virsh domstate web01
virsh vcpuinfo web01
virsh dommemstat web01
virsh dumpxml web01
virsh edit web01
```

## Domain XML: the important elements

```xml
<domain type='kvm'>
  <name>web01</name>
  <memory unit='MiB'>4096</memory>
  <vcpu>4</vcpu>
  <os><type arch='x86_64'>hvm</type></os>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='/var/lib/libvirt/images/web01.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='bridge'>
      <source bridge='br0'/>
      <model type='virtio'/>
    </interface>
  </devices>
</domain>
```

Reading XML is a practical skill: it is how you answer “what bus is the disk
on?”, “how much RAM?”, “which network?”, and “what snapshots exist?” without
booting the guest. `xml.etree.ElementTree` parses it in Python.

Policy checks a reviewer makes on every new VM:

- disk bus is `virtio` (not `ide` or `sata`),
- NIC model is `virtio`,
- memory and vCPU match the request,
- the disk source is on the intended storage pool,
- at least one snapshot or backup exists, and
- the network matches the intended exposure (bridged = public, NAT = private).

## VirtIO and paravirtualization

Fully emulated devices (IDE, e1000, VGA) are compatible but slow because every
I/O goes through emulation. **VirtIO** devices are paravirtual: the guest knows
it is virtual and uses a shared-memory ring to talk to the host. That gives
near-native disk and network performance.

- disk: `virtio-blk` or `virtio-scsi` (bus `virtio` / `scsi`),
- network: `virtio-net`,
- balloon: `virtio-balloon` for memory reclaim,
- serial/console: `virtio-serial`, `virtio-console`,
- GPU: `virtio-gpu` (display) or VFIO passthrough (compute).

Linux guests have VirtIO drivers built in or in the initramfs. Windows guests
need the VirtIO driver ISO during installation. If a guest cannot see its disk,
the first question is whether the VirtIO driver is present in its initrd.

## Disk images

Common formats:

| Format | Use |
|---|---|
| `raw` | simple, fast, no snapshot support in QEMU; full size |
| `qcow2` | copy-on-write, snapshots, compression, thin provisioning |
| `vmdk` / `vdi` / `vhdx` | importing/exporting to other hypervisors |
| `iso` | installation media |

`qemu-img` inspects and manipulates images:

```bash
qemu-img info web01.qcow2
qemu-img create -f qcow2 web01.qcow2 40G
qemu-img convert -f qcow2 -O raw web01.qcow2 web01.raw
qemu-img convert -O qcow2 -c web01.raw web01.qcow2   # -c compresses
qemu-img resize web01.qcow2 +20G
qemu-img snapshot -l web01.qcow2
qemu-img check web01.qcow2
```

Resizing an image only changes the virtual disk size. The guest must then grow
the partition and the filesystem (module 3):

```bash
# inside the guest
sudo growpart /dev/vda 1
sudo resize2fs /dev/vda1        # ext4
sudo xfs_growfs /               # XFS
```

## Templates, cloning, and migration

### Baseline templates

Build a clean, patched, minimal image with cloud-init installed. Mark it
read-only and clone from it; never boot the template itself for daily work.
This gives reproducible VMs and avoids configuration drift.

### Cloning

```bash
virt-clone --original template --name web02 \
  --file /var/lib/libvirt/images/web02.qcow2
```

A clone must get new identity: hostname, machine-id, SSH host keys, and IP
address. Cloud-init or `sysprep`-style first-boot scripts handle that. Cloning
without regenerating SSH host keys creates a security problem (two hosts with
the same key) and cloning without changing the IP causes an address conflict.

### Snapshots

There are two kinds:

- **internal** — stored inside a qcow2 file (`virsh snapshot-create-as`,
  `qemu-img snapshot`). Simple, but tied to the image format.
- **external** — separate overlay files, often with a backing file. Better for
  production and for snapshots while running.

```bash
virsh snapshot-create-as web01 before-upgrade "before package upgrade"
virsh snapshot-list web01
virsh snapshot-revert web01 before-upgrade
virsh snapshot-delete web01 before-upgrade
```

A snapshot is not a backup. It lives on the same storage, depends on the base
image, and is lost if the storage fails. Back up the image or use the guest's
own backup tool.

### Migration

- **Cold migration:** shut down, move the disk and XML, start elsewhere.
- **Live migration:** copy RAM and state while running, with shared storage or
  block migration. Needs compatible CPU flags, network connectivity, and
  libvirt access on both hosts.

```bash
virsh migrate --live web01 qemu+ssh://host2/system
```

Nested virtualization means running KVM inside a guest. It requires the host
to expose `vmx`/`svm` to the guest (`<cpu mode='host-passthrough'/>` and
`<feature policy='require' name='vmx'/>`), and it is slower.

## Network types

| Type | Guest can reach | Typical use |
|---|---|---|
| **Bridged** | the physical LAN, gets a LAN IP | servers that must be visible |
| **NAT** | outbound via the host, not inbound by default | laptops, isolated labs |
| **Host-only / isolated** | host and other guests only | testing, no internet |
| **Routed** | other networks via host routing rules | controlled multi-subnet labs |
| **Open** | no filtering; all traffic passes | special appliances (careful!) |

```bash
virsh net-list --all
virsh net-dumpxml default
virsh net-start default
virsh net-autostart default
ip link show virbr0
```

The libvirt `default` network is NAT with `virbr0` at 192.168.122.1/24. Port
forwarding is done with firewalld/nftables rules, not by the VM itself.

Network performance follows the same rule as disks: `virtio` model, not
emulated e1000. For very high throughput, use vhost-net, SR-IOV VFs, or
passthrough.

## Bare metal versus virtual machines

| | Bare metal | Virtual machine |
|---|---|---|
| Performance | full, no hypervisor tax | near-native with VirtIO/KVM |
| Hardware access | direct | emulated or passthrough |
| Density | one OS per host | many guests per host |
| Snapshots/clones | storage-dependent | built into the platform |
| Failure domain | whole host | one guest (host failure still hurts all) |
| Licensing | per host | per socket/core or per guest |

Virtualization does not remove the need for backups, monitoring, or patching.
It changes the failure modes: noisy neighbours, host resource exhaustion,
storage latency, and clone identity mistakes.

## Mission 06 — what you build

`vms/web01.xml` and `vms/db01.xml` are libvirt domain definitions;
`fixtures/snapshots.txt` is `virsh snapshot-list` output. Your
`vm_audit.py --dir vms --snapshots fixtures/snapshots.txt` must emit:

- `vms` — for each name: `memory_mib`, `vcpus`, `disk_bus`, `disk_source`,
  `network_type`, `network_source`, `domain_type`, `snapshots`,
- `issues` — one string per policy violation, naming the VM and the reason.

Policy: VirtIO disk bus, at least 2048 MiB RAM, at least one snapshot. Parse
the XML with `xml.etree.ElementTree`, including `source` *attributes* such as
`file=`, `bridge=`, and `network=`. Run `python3 main.py verify 6`.

## Exam traps

- `virsh destroy` is not “delete”; it is an immediate power-off.
- `virsh undefine` removes the definition but not the disk unless you ask.
- A qcow2 snapshot is not a backup.
- `qemu-img resize` does not grow the guest filesystem.
- Bridged networking exposes the guest directly to the LAN; NAT does not.
- Emulated devices work everywhere but VirtIO is the performance answer.

## Check yourself

1. Which kernel module provides hardware acceleration, and how do you verify it
   is available?
2. What is the difference between QEMU and KVM?
3. Why is VirtIO faster than an emulated e1000 NIC?
4. How do you convert a qcow2 image to raw, and why might you?
5. What must change after cloning a VM?
6. Which libvirt network type gives a guest a LAN-visible address?

## Going deeper

- Read `man 5 domain.xml` (or the libvirt XML documentation online).
- Create a VM with `virt-install`, convert its disk to raw, and boot it.
- Take an internal and an external snapshot and compare the files on disk.
- Use `virsh domblklist`, `domiflist`, and `dumpxml` to map a running VM.

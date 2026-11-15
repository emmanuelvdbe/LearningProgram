# Module 2 — Kernel modules, devices, and initrd

> **Exam objective:** Linux+ 1.2 — Summarize Linux device management concepts
> and tools.
> **Study time:** about 90 minutes, including the mission.
> **Mission:** `device_audit.py` — inspect realistic module, PCI, CPU, dmesg,
> and initrd fixtures and produce a hardware report.

## What the exam expects

Objective 1.2 is about how Linux discovers hardware and how drivers are loaded.
You need to know:

- the kernel-module tools (`lsmod`, `modinfo`, `modprobe`, `insmod`, `rmmod`,
  `depmod`) and when to use each,
- how to read the kernel log (`dmesg`) and hardware inventories (`lspci`,
  `lsusb`, `lscpu`, `lshw`, `lsmem`, `dmidecode`, `lm_sensors`, `ipmitool`),
- how the initrd is built and inspected (`dracut`, `mkinitrd`, `lsinitrd`),
- the special cases: embedded systems, GPUs (`nvtop`), and SR-IOV.

A large share of “the server will not boot / the NIC disappeared / the GPU is
not used” incidents reduce to a missing or broken module.

## The kernel and modules

A monolithic kernel with loadable modules gives you both speed and
flexibility. Core code is always present; drivers can be inserted at runtime.

```bash
lsmod                 # modules currently loaded (name, size, refcount, users)
lsmod | head
modinfo e1000e        # description, author, licence, parameters, aliases
modinfo -F parm e1000e
```

`lsmod` reads `/proc/modules`. A module with a non-zero “Used by” count cannot
be removed until its users are gone.

### Loading and unloading

| Tool | Use it when |
|---|---|
| `modprobe` | normal choice: resolves dependencies and aliases |
| `insmod` | you have one `.ko` file and want no dependency handling |
| `rmmod` | remove a module that is no longer in use |
| `modprobe -r` | remove a module *and* modules that depend on it |
| `depmod -a` | rebuild `modules.dep` after adding a module by hand |

```bash
sudo modprobe e1000e
sudo modprobe -r e1000e
sudo insmod ./mydriver.ko
sudo rmmod mydriver
sudo depmod -a
```

`modprobe` reads `/lib/modules/$(uname -r)/modules.dep` and
`modules.alias`. If you copy a module into the tree manually, run `depmod -a`
or `modprobe` will not find it.

### Persisting a module

A one-off `modprobe` disappears at reboot. To load a module automatically:

```bash
# Debian/Ubuntu
echo e1000e | sudo tee /etc/modules-load.d/e1000e.conf
# RHEL/Fedora and most systemd distributions
echo e1000e | sudo tee /etc/modules-load.d/e1000e.conf
```

For module options:

```bash
echo 'options e1000e InterruptThrottleRate=3000' | \
  sudo tee /etc/modprobe.d/e1000e.conf
```

Blacklisting prevents automatic loading (not a security boundary — a user with
root can still load it):

```bash
echo 'blacklist nouveau' | sudo tee /etc/modprobe.d/blacklist-nouveau.conf
sudo dracut -f
```

### Kernel messages

`dmesg` is the kernel ring buffer: hardware detection, driver binding, link
up/down, I/O errors, OOM kills, filesystem errors.

```bash
dmesg --level=err,warn
dmesg -T | tail -50          # human timestamps
dmesg | grep -i -E 'error|fail'
journalctl -k -b             # kernel messages for this boot via systemd
```

The ring buffer is volatile. Persistent kernel logs come from `journald` or
`rsyslog` (module 12). When a device fails, `dmesg` usually names the device
and the driver before any higher-level service complains.

## Hardware inventory tools

### PCI and USB

```bash
lspci                     # all PCI devices
lspci -nnk                # numeric IDs and the kernel driver in use
lspci -s 00:1f.2 -vv      # one device, verbose
lsusb                     # USB devices
lsusb -t                  # USB topology and speeds
```

`lspci -nnk` is the fastest way to answer “which driver owns this NIC?”. If
“Kernel driver in use” is missing, no module claimed the device.

### CPU, memory, firmware

```bash
lscpu                     # architecture, model, cores, threads, flags (vmx/svm)
lscpu | grep -E 'Architecture|Virtualization|Model name'
lsmem                     # memory ranges, online/offline
lshw -short               # whole hardware tree (may need root)
sudo dmidecode -t system  # BIOS/UEFI vendor, serial, VM detection
sudo dmidecode -t memory  # DIMM slots and sizes
```

`dmidecode` reads SMBIOS/DMI tables. In a VM it often shows “QEMU”,
“VirtualBox”, or “VMware” as the system vendor — a quick way to confirm
virtualisation (module 6).

### Sensors and out-of-band management

```bash
lm_sensors: sensors       # CPU/board temperatures, fan speeds, voltages
ipmitool sensor list      # out-of-band BMC data on real servers
nvtop                     # GPU utilisation (NVIDIA/AMD/Intel)
nvidia-smi                # NVIDIA-specific equivalent
```

Servers expose hardware health through a BMC (IPMI/Redfish). `ipmitool` can
read sensors, the event log, and power state even when the OS is down. That is
why “server will not turn on” is often an IPMI question (5.2).

## initrd management

The initramfs (often still called initrd) is a compressed cpio archive loaded
with the kernel. It contains the modules and scripts needed to find the real
root.

```bash
# Inspect
lsinitrd /boot/initramfs-$(uname -r).img | less
lsinitrd /boot/initramfs-$(uname -r).img | grep e1000e
lsinitramfs /boot/initrd.img-$(uname -r) | less      # Debian-family

# Rebuild
sudo dracut -f /boot/initramfs-$(uname -r).img $(uname -r)
sudo dracut --add-drivers "e1000e" -f
sudo update-initramfs -u                              # Debian wrapper
sudo mkinitrd -f /boot/initrd.img-$(uname -r) $(uname -r)
```

`dracut` is the standard on RHEL/Fedora/SUSE and is available on Debian too.
Its configuration lives in `/etc/dracut.conf` and `/etc/dracut.conf.d/`.
`DRACUT_KMODDIR_OVERRIDE`, `add_drivers`, and `omit_drivers` are common
settings.

### When the initrd matters

- Root on LVM, LUKS, RAID, iSCSI, or NFS: the initrd must contain the storage
  and network stack.
- New NIC or storage controller: add the driver, rebuild the initrd, *then*
  reboot.
- Kernel upgrade: the package usually rebuilds the initrd automatically; if
  it fails, the new kernel panics at boot.
- A missing `root=` or wrong UUID is a GRUB problem, not an initrd problem —
  but the symptom can look identical.

## Embedded systems and custom hardware

Linux runs on routers, PLCs, cars, and single-board computers. The principles
are the same, with different constraints:

- device tree (`/boot/*.dtb`) describes hardware instead of ACPI,
- storage may be eMMC, NAND, or read-only squashfs,
- serial console (`console=ttyS0`) is often the only console,
- modules may be built into the kernel to avoid an initrd entirely,
- cross-compilation produces binaries for the target architecture.

For the exam, recognise that “custom hardware” means a vendor kernel, device
tree, and possibly out-of-tree modules. `modinfo` on a vendor module shows its
`vermagic`; a module built for a different kernel version refuses to load.

## GPUs and SR-IOV

- **GPU use cases:** CUDA/ROCm compute, transcoding, virtual desktops, AI.
  `nvtop` shows per-GPU and per-process utilisation.
- **VFIO passthrough:** bind the GPU to `vfio-pci` and give the VM direct
  access (module 6).
- **SR-IOV:** one physical NIC presents multiple virtual functions (VFs).
  Enable it in firmware, set the number of VFs
  (`echo 8 > /sys/class/net/eth0/device/sriov_numvfs`), and assign VFs to VMs
  for near-native network performance.

## Mission 02 — what you build

`fixtures/` contains captured output from `lsmod`, `lspci`, `dmesg`, `lscpu`,
`modinfo`, and `lsinitrd`. Your `device_audit.py --fixtures fixtures` must
report:

- `loaded_modules` — names in `lsmod` file order,
- `gpu_pci` and `nic_pci` — PCI addresses of the VGA and Ethernet controllers,
- `module_errors` — `dmesg` lines containing `failed` or `error` (any case),
- `cpu_arch` — the `Architecture:` value from `lscpu`,
- `virtualization` — `vt-x` for `vmx`, `amd-v` for `svm`, otherwise `none`,
- `initrd_has_e1000e` — whether `e1000e.ko` appears in the initrd listing,
- `e1000e_license` — the licence line from `modinfo`.

Everything must be parsed from the fixtures. Run `python3 main.py verify 2`.

## Exam traps

- `insmod` does not resolve dependencies; `modprobe` does.
- “Used by” counts include modules that depend on this one, not just processes.
- `dmesg` shows hardware events, but `journalctl -k` is the persistent view.
- `lspci` shows the device; `lspci -k` shows whether a driver is bound.
- Blacklisting is a convenience, not a security control.
- Rebuilding the initrd does not change GRUB; regenerating GRUB does not
  rebuild the initrd.

## Check yourself

1. Which command shows a module's parameters and licence?
2. A NIC is visible in `lspci` but has no driver in use. What do you check
   next?
3. You added a module under `/lib/modules/$(uname -r)/extra`. What must you
   run before `modprobe` finds it?
4. What does `dracut -f` do, and when is it required?
5. Where would you look for a hardware error that happened before the OS
   started logging to disk?
6. How do you confirm that a machine is a virtual machine using DMI data?

## Going deeper

- Run `lsmod`, `lspci -nnk`, and `lscpu` on your own machine and map each PCI
  device to its driver.
- Read `man 5 modprobe.d` and `man 8 dracut`.
- Compare `lsinitrd` on a distribution with a minimal and a full initramfs.
- Explore `/sys/class/net/<iface>/device/` for driver and firmware details.

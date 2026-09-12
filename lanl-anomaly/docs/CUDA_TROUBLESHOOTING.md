# CUDA Troubleshooting

## Problem: `cuInit(0)` fails with error 999

### Symptom

```
torch.cuda.is_available() → False
CUDA initialization: CUDA unknown error
cuInit(0) = 999 (CUDA_ERROR_UNKNOWN)
```

`nvidia-smi` works fine, GPU is detected, but PyTorch can't use CUDA.

### Environment

- GPU: NVIDIA GeForce RTX 3050 (6GB VRAM)
- Driver: 580.173.02 (open kernel module)
- CUDA version: 13.0
- OS: Pop!_OS with Cosmic desktop (Wayland)
- PyTorch: 2.11.0+cu128

### Root Cause

The `nvidia_uvm` (Unified Virtual Memory) kernel module is not loaded.
Cosmic desktop may unload it during power management or startup.

Without `nvidia_uvm`, the CUDA driver API (`cuInit`) fails even though
the GPU is visible to `nvidia-smi`.

### Fix (per session)

```bash
pkexec modprobe nvidia_uvm
```

### Fix (persistent across reboots)

```bash
echo "nvidia_uvm" | pkexec tee /etc/modules-load.d/nvidia.conf
```

### Verify

```python
import torch
print(torch.cuda.is_available())  # Should print True
print(torch.cuda.get_device_name(0))  # Should print GPU name
```

### Reference

- https://github.com/NVIDIA/open-gpu-kernel-modules/issues/689
- Affects: RTX 3050 + open kernel module + Cosmic/Wayland

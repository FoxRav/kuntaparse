"""Paddle runtime device selection.

Policy:
- Use GPU if `use_gpu=True` AND Paddle is compiled with CUDA.
- Otherwise stay on CPU and print an actionable message once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PaddleDeviceInfo:
    requested_gpu: bool
    cuda_compiled: bool
    selected_device: str
    note: Optional[str]


_WARNED: bool = False


def configure_paddle_device(*, use_gpu: bool) -> PaddleDeviceInfo:
    global _WARNED
    try:
        import paddle  # type: ignore[import-not-found]
    except Exception:
        return PaddleDeviceInfo(
            requested_gpu=use_gpu,
            cuda_compiled=False,
            selected_device="unknown",
            note="Paddle is not importable; cannot set device.",
        )

    cuda_compiled = bool(getattr(paddle, "is_compiled_with_cuda", lambda: False)())
    if use_gpu and cuda_compiled:
        try:
            paddle.set_device("gpu:0")
            return PaddleDeviceInfo(
                requested_gpu=True,
                cuda_compiled=True,
                selected_device=str(paddle.get_device()),
                note=None,
            )
        except Exception as e:
            # Fall back to CPU, but be explicit.
            try:
                paddle.set_device("cpu")
            except Exception:
                pass
            if not _WARNED:
                print(
                    "WARNING: GPU was requested but Paddle failed to select GPU; "
                    f"falling back to CPU. Reason: {e}"
                )
                _WARNED = True
            return PaddleDeviceInfo(
                requested_gpu=True,
                cuda_compiled=True,
                selected_device=str(paddle.get_device()),
                note=f"Failed to set gpu:0: {e}",
            )

    # CPU path
    try:
        paddle.set_device("cpu")
    except Exception:
        pass

    if use_gpu and not cuda_compiled and not _WARNED:
        print(
            "WARNING: GPU is available, but Paddle is a CPU build (paddle.is_compiled_with_cuda()=False). "
            "PP-Structure will run on CPU. To enable GPU, install a Paddle GPU wheel "
            "compatible with your CUDA driver (see README)."
        )
        _WARNED = True

    return PaddleDeviceInfo(
        requested_gpu=use_gpu,
        cuda_compiled=cuda_compiled,
        selected_device=str(paddle.get_device()),
        note=None if (not use_gpu or cuda_compiled) else "CPU Paddle build detected.",
    )



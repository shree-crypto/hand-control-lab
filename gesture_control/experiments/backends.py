# SPDX-License-Identifier: GPL-3.0-only
"""Optional model/backend inspection; default reports never load model runtimes."""
import argparse
import importlib.metadata
import importlib.util
import json
import math
from pathlib import Path
import platform
import sys
import time


PACKAGES = {
    "mediapipe": "mediapipe",
    "onnxruntime": "onnxruntime",
    "whircam": "whircam",
    "eyetrax": "eyetrax",
    "wilor_mini": "wilor-mini",
    "torch": "torch",
}


def package_status(module, distribution):
    try:
        found = importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, AttributeError):
        found = False
    try:
        version = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        version = None
    return {"module_available": found, "distribution_version": version}


def capability_report(probe=False):
    report = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "packages": {name: package_status(name, dist) for name, dist in PACKAGES.items()},
        "runtime_probed": probe,
        "notes": [
            "Default report inspects module and distribution metadata only; no model is loaded.",
            "Current hand experiments use MediaPipe CPU inference; NPU acceleration is not integrated.",
            "Installed providers do not prove any model runs on that hardware.",
            "CUDA support is not AMD Ryzen AI NPU support.",
            "AMD CVML is a separate C++ SDK; no CVML Python adapter is claimed here.",
        ],
    }
    if probe:
        try:
            import onnxruntime
            report["onnxruntime_available_providers"] = list(onnxruntime.get_available_providers())
        except Exception as exc:
            report["onnxruntime_probe_error"] = f"{type(exc).__name__}: {exc}"[:500]
        try:
            import torch
            report["torch_cuda_available"] = bool(torch.cuda.is_available())
            report["torch_cuda_version"] = torch.version.cuda
            report["torch_hip_version"] = getattr(torch.version, "hip", None)
        except Exception as exc:
            report["torch_probe_error"] = f"{type(exc).__name__}: {exc}"[:500]
    return report


def summarize(value, depth=0):
    """Bounded structural output: arrays/tensors are described, never serialized."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        return value[:240]
    if depth >= 4:
        return {"type": type(value).__name__, "truncated": True}
    shape = getattr(value, "shape", None)
    if shape is not None:
        try:
            dimensions = [int(dimension) for dimension in list(shape)[:12]]
        except (TypeError, ValueError):
            dimensions = ["unknown"]
        return {"type": type(value).__name__, "shape": dimensions,
                "dtype": str(getattr(value, "dtype", "unknown"))[:100]}
    if isinstance(value, dict):
        result = {str(key)[:100]: summarize(item, depth + 1)
                  for key, item in list(value.items())[:20]}
        if len(value) > 20:
            result["_omitted_entries"] = len(value) - 20
        return result
    if isinstance(value, (list, tuple)):
        items = [summarize(item, depth + 1) for item in value[:20]]
        if len(value) > 20:
            items.append({"omitted_items": len(value) - 20})
        return items
    return {"type": type(value).__name__}


def validate_image(path):
    image = Path(path).expanduser().resolve()
    if not image.is_file():
        raise ValueError(f"Image does not exist: {image}")
    if image.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
        raise ValueError("Use a PNG, JPEG, BMP, or WebP image.")
    if image.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Image exceeds the 50 MiB input limit.")
    return image


def reconstruct(path, device="cpu"):
    image_path = validate_image(path)
    print("WiLoR is optional. Initializing it may download upstream model assets. "
          "Review WiLoR/MANO model licenses before redistribution.", file=sys.stderr, flush=True)
    try:
        import cv2
        import torch
        from wilor_mini.pipelines.wilor_hand_pose3d_estimation_pipeline import WiLorHandPose3dEstimationPipeline
    except ImportError as exc:
        raise RuntimeError("Optional mesh dependencies are missing. See docs/backends.md; "
                           "install them in a separate environment.") from exc
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable. Use --device cpu; AMD NPU is not CUDA.")
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError("OpenCV could not decode this image.")
    if image.shape[0] * image.shape[1] > 20_000_000:
        raise ValueError("Decoded image exceeds 20 megapixels; resize it first.")
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    started = time.perf_counter()
    pipeline = WiLorHandPose3dEstimationPipeline(device=torch.device(device), dtype=torch.float32)
    initialized = time.perf_counter()
    with torch.inference_mode():
        outputs = pipeline.predict(rgb)
    if device == "cuda":
        torch.cuda.synchronize()
    finished = time.perf_counter()
    return {"model": "WiLoR-mini", "device_requested": device,
            "initialization_seconds": round(initialized - started, 4),
            "inference_seconds": round(finished - initialized, 4),
            "image_dimensions": [int(image.shape[1]), int(image.shape[0])],
            "output_summary": summarize(outputs),
            "note": "Single-image experiment, not a real-time or precision benchmark. No mesh file exported."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doctor", action="store_true", help="Report optional packages (default)")
    parser.add_argument("--probe", action="store_true", help="Explicitly import ONNX Runtime/Torch and query providers")
    parser.add_argument("--mesh", type=Path, metavar="IMAGE", help="Explicitly run optional WiLoR-mini image reconstruction; may download models")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--output", type=Path, help="Write JSON report to this path")
    args = parser.parse_args(argv)
    if args.mesh and (args.doctor or args.probe):
        parser.error("Run --mesh separately from --doctor/--probe.")
    try:
        result = reconstruct(args.mesh, args.device) if args.mesh else capability_report(args.probe)
        encoded = json.dumps(result, indent=2, allow_nan=False)
        if args.output:
            args.output.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Backend experiment stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

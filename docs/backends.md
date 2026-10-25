# Optional backends: diagnostics and hand-mesh experiment

The normal hand controller and webcam experiments currently use MediaPipe CPU inference. This feature does not enable AMD NPU acceleration. It provides a lightweight inventory and an optional isolated WiLoR image experiment.

## Inspect optional packages

```powershell
python -m gesture_control backends --doctor
python -m gesture_control backends --probe --output backend-report.json
```

The default/`--doctor` path reads package metadata and module availability without importing model runtimes, installing packages, accessing cameras or downloading models. `--probe` explicitly imports ONNX Runtime and PyTorch, when installed, to query available providers and CUDA/HIP runtime metadata. An available provider does not prove a particular model executes on it; verify actual provider selection and timings during inference. CUDA availability is not AMD NPU support.

## WiLoR-mini image reconstruction

This is optional and intentionally not in the main requirements. Use a separate Python 3.10 environment, following [WiLoR-mini's upstream instructions](https://github.com/warmshao/WiLoR-mini). Install PyTorch, OpenCV and the upstream package according to their current documented compatibility. Do not install arbitrary CUDA packages into the hand-controller environment; this Ryzen laptop does not imply NVIDIA CUDA support.

From the project folder using the separate environment:

```powershell
python -m gesture_control backends --mesh hand-photo.jpg --device cpu --output mesh-report.json
```

`--mesh` explicitly initializes the optional model and may download upstream model assets. It prints that fact before loading them. Review [WiLoR](https://github.com/rolpotamias/WiLoR) and MANO asset licenses before reuse or redistribution. `--device cuda` is supported only when explicitly requested and PyTorch reports CUDA availability. CPU uses float32 rather than assuming half-precision CPU support.

The output is a bounded structural JSON summary of predicted tensors/arrays plus initialization and single-image inference times. It does not export a mesh asset, capture video, operate the mouse, or claim real-time performance. Network/model setup may take time and is outside the fast metadata report. This integration has not been tested with downloaded models or on the user's hardware.

## AMD Ryzen AI CVML path

AMD's [CVML documentation](https://ryzenai.docs.amd.com/en/latest/ryzen_ai_libraries.html) and [vision playbook](https://developer.amd.com/playbooks/cvml/) describe a **C++ SDK** for face detection, face meshes and estimated RGB depth. No fabricated Python API is provided here.

To evaluate it separately:

1. Verify Ryzen AI 5 330 support in AMD's current platform requirements and check the laptop's OEM/AMD driver recommendations.
2. Obtain the CVML SDK from AMD and review its license. Install its documented OpenCV/CMake/MSVC prerequisites in a separate native development setup.
3. Build the SDK's included face-detection or face-mesh sample with its documented CMake configuration. Start with an image, then webcam input.
4. Record actual backend selection, resolution, warm-up, average and tail inference latency, and CPU/GPU/NPU utilization. Compare against the same input in MediaPipe. First-run compilation/loading time must be recorded separately from steady-state inference.
5. Integrate only after measuring a benefit. Provider support and model/operator compatibility matter; NPU marketing TOPS are not an application benchmark.

CVML's predicted RGB depth is not measured depth from a physical depth sensor, and neither establishes accurate millimeter CAD measurements. WHIRCAM availability likewise does not prove a depth stream exists.

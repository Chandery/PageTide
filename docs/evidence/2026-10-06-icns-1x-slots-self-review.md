# Self-review: 2026-10-06-icns-1x-slots

Scope: icon.icns packaging and the 16/32 px icon masters only. No runtime, model, network or data path touched.

- Defect 1 (noise on the external display) was reproduced with iconutil before the change (random pixels in
  the 16/32 px 1x slots, from PNG stored under icp4/icp5) and is gone after it, using the same decoder.
  This is a decoder-level check, not a check on the owner's display.
- The 1x slots are now ic04/ic05 ("ARGB" + RLE planes), the layout Apple's iconutil writes; the layout was
  checked by decoding VS Code's Code.icns the same way. The ic05 planes are asserted equal, channel by
  channel, to the PNG of the same 32 px master. RLE edge cases (runs >130, literals >128, runs of 2) are
  round-trip tested.
- Defect 2 (weak small icon: 1.4 px bookmark blending to pink, 20% margin) was addressed with tuned 16/32 px
  masters, compared at real size before choosing. ic11 (Retina 16pt) uses the 32 px master, so Retina
  Finder-list icons change slightly; 64 px and up are unchanged.
- build_icons.py remains standard-library only (own PNG decoder for the rasterizer's 8-bit RGBA output); it
  asserts if the rasterizer ever emits another PNG layout.

Open: the external display still shows a small icon with a grey rim. The owner's screenshot shows many other
apps rendered the same way, so this is treated as macOS-wide behaviour; the agent could not render real icons
in its sandbox and did not establish the cause. Independent review not performed.

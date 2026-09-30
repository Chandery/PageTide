// Rasterizes an SVG to a square PNG with AppKit's built-in SVG support.
// Usage: swift rasterize.swift <in.svg> <out.png> <pixels>
import AppKit
let a = CommandLine.arguments
guard a.count == 4, let img = NSImage(contentsOf: URL(fileURLWithPath: a[1])), let px = Int(a[3]) else {
  FileHandle.standardError.write("usage: rasterize <in.svg> <out.png> <px>\n".data(using: .utf8)!); exit(1) }
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px, bitsPerSample: 8,
  samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
rep.size = NSSize(width: px, height: px)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
NSGraphicsContext.current?.imageInterpolation = .high
img.draw(in: NSRect(x: 0, y: 0, width: px, height: px))
NSGraphicsContext.restoreGraphicsState()
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: a[2]))

"""One-page PDF with real offsets; synthetic metadata remains test-only."""
def minimal_pdf(label='fixture'):
    label = str(label).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    content = ('BT /F1 12 Tf 10 10 Td (' + label + ') Tj ET').encode('utf-8')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
               b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    out, offsets = bytearray(b'%PDF-1.4\n'), [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out.extend(str(i).encode() + b' 0 obj\n' + obj + b'\nendobj\n')
    xref = len(out)
    out.extend(b'xref\n0 6\n0000000000 65535 f \n')
    for offset in offsets[1:]:
        out.extend(f'{offset:010} 00000 n \n'.encode())
    out.extend(b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n' + str(xref).encode() + b'\n%%EOF\n')
    return bytes(out)

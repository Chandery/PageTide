"""Bounded, non-executing PDF envelope checks before accepting an archive.

This checks the end marker and cross-reference anchor, not PDF rendering, OCR,
password access, or every page object. It rejects header-only/truncated uploads
without introducing a PDF interpreter into the download worker.
"""
import io
import re
from pathlib import Path


def _dictionary_fields(stream, offset, size, is_stream=False):
    """Scan bounded chunks to the envelope end, retaining only needed fields.

    PDF permits large dictionaries and arbitrary field order. Neither the xref
    row count nor the Index array is limited by our chunk size.
    """
    stream.seek(offset)
    carry, fields = b'', {}
    # A comment counts as whitespace in PDF (iText writes one between a trailer's >> and startxref: a Springer PDF was
    # refused as "缺少索引字典结束信息", 2026-10-26).
    gap = rb'(?:\s|%[^\r\n]*(?:\r\n|\r|\n))*'
    stop = rb'>>' + gap + rb'stream(?:\r\n|\r|\n)' if is_stream else rb'>>' + gap + rb'startxref\b'
    while stream.tell() < size:
        chunk = stream.read(min(65536, size - stream.tell()))
        piece = carry + chunk
        end = re.search(stop, piece)
        visible = piece[:end.start()] if end else piece
        for field in re.findall(rb'/Root\s+\d+\s+\d+\s+R\b|/Prev\s+\d+\b|/Type\s*/XRef\b', visible):
            fields.setdefault(field.split()[0], field)
        if end:
            return b' '.join(fields.values())
        carry = piece[-128:]
    raise ValueError('PDF 缺少索引字典结束信息')


def _xref_dictionary(stream, offset, size):
    """Read a table's trailer separately from its potentially large row body."""
    stream.seek(offset)
    anchor = stream.read(min(4096, size - offset))
    if re.match(rb'xref\b', anchor):
        stream.seek(offset)
        carry = b''
        while stream.tell() < size:
            chunk = stream.read(min(65536, size - stream.tell()))
            piece = carry + chunk
            marker = re.search(rb'\btrailer\b', piece)
            if marker:
                start = stream.tell() - len(piece) + marker.end()
                stream.seek(start)
                return _dictionary_fields(stream, start, size)
            carry = piece[-16:]
        raise ValueError('PDF 缺少索引结束信息')
    if re.match(rb'\d+\s+\d+\s+obj\b', anchor):
        # Scan to the stream boundary without decoding any stream bytes.
        fields = _dictionary_fields(stream, offset, size, is_stream=True)
        if re.search(rb'/Type\s*/XRef\b', fields):
            return fields
    raise ValueError('PDF 索引位置无效，文件可能已损坏')


def validate_pdf(source):
    owned = isinstance(source, (str, Path, bytes, bytearray))
    stream = (io.BytesIO(bytes(source)) if isinstance(source, (bytes, bytearray))
              else Path(source).open('rb') if isinstance(source, (str, Path)) else source)
    try:
        stream.seek(0, 2)
        size = stream.tell()
        if size > 60 * 1024 * 1024:
            raise ValueError('PDF 超过 60 MB，无法导入')
        stream.seek(0)
        head = stream.read(min(size, 1024))
        if not re.search(rb'%PDF-[12]\.\d', head):
            raise ValueError('这不是 PDF 文件')
        stream.seek(max(0, size - 65536))
        tail = stream.read(65536)
        ends = list(re.finditer(rb'startxref\s+(\d+)\s+%%EOF\s*$', tail))
        if not ends:
            raise ValueError('PDF 不完整或缺少有效结尾，请重新下载或选择完整文件')
        offset = int(ends[-1].group(1))
        if offset < 8 or offset >= size:
            raise ValueError('PDF 索引位置无效，文件可能已损坏')
        for _ in range(128):
            dictionary = _xref_dictionary(stream, offset, size)
            root = re.search(rb'/Root\s+(\d+)\s+\d+\s+R\b', dictionary)
            if root and int(root.group(1)) > 0:
                return True
            # Incremental updates may inherit Root from an earlier trailer.
            prev = re.search(rb'/Prev\s+(\d+)\b', dictionary)
            previous = int(prev.group(1)) if prev else 0
            if not 8 <= previous < offset:
                break
            offset = previous
        raise ValueError('PDF 缺少有效根目录，请重新获取完整文件')
    finally:
        if owned:
            stream.close()

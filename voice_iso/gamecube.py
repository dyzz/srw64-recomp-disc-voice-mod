"""GameCube and Wii discs: the file table, Dolphin's RVZ images (a Wii one's game partition, which RVZ keeps
decrypted), Nintendo DSP ADPCM and CRI ADX."""
from __future__ import annotations

import math
import struct
from pathlib import Path

import numpy as np


class Rvz:
    """A GameCube RVZ image read by disc offset: groups of zstd data (Dolphin's docs/WiaAndRvz.md). The padding the
    disc made from a random seed comes back as zeros; no file lies in it."""

    def __init__(self, path: Path):
        try:
            import zstandard
        except ImportError:
            raise RuntimeError(f"{path.name}: an .rvz needs zstandard (pip install zstandard), or Dolphin's "
                               "Convert File to make it an .iso") from None
        self.z = zstandard.ZstdDecompressor()
        self.f = path.open("rb")
        h1 = self.f.read(0x48)
        h2 = self.f.read(struct.unpack_from(">I", h1, 12)[0])
        self.disc, compression, _, self.chunk = struct.unpack_from(">IIiI", h2, 0)
        if self.disc not in (1, 2) or compression != 5:
            raise ValueError(f"{path.name}: not a GameCube or Wii RVZ with zstd (disc type {self.disc}, compression {compression})")
        self.head = h2[16:16 + 0x80]
        nparts, partsize, partoff = struct.unpack_from(">IIQ", h2, 16 + 0x80)
        nraw, rawoff, rawsize, ngroups, groupoff, groupsize = struct.unpack_from(">IQIIQI", h2, 16 + 0x80 + 36)
        raw = self._table(rawoff, rawsize)
        groups = self._table(groupoff, groupsize)
        self.raw = [struct.unpack_from(">QQII", raw, i * 24) for i in range(nraw)]
        self.groups = [struct.unpack_from(">III", groups, i * 12) for i in range(ngroups)]
        self.cached = (-1, b"")
        if self.disc == 2:   # Wii: the game partition (the biggest), its data entries (first sector, sectors, group, groups)
            self.f.seek(partoff)
            p = self.f.read(nparts * partsize)
            parts = [[struct.unpack_from(">IIII", p, i * partsize + 16 + 16 * j) for j in range(2)] for i in range(nparts)]
            self.partition = max(parts, key=lambda e: e[0][1] + e[1][1])

    def _table(self, offset: int, size: int) -> bytes:
        self.f.seek(offset)
        return self.z.decompressobj().decompress(self.f.read(size))

    def _group(self, i: int, length: int, wii: bool = False) -> bytes:
        if self.cached[0] == i:
            return self.cached[1]
        offset, size, packed = self.groups[i]
        data = bytes(length)
        if size & 0x7FFFFFFF:
            self.f.seek(offset << 2)
            data = self.f.read(size & 0x7FFFFFFF)
            if size >> 31:
                data = self.z.decompressobj().decompress(data)
            if wii:   # the hash exceptions first: a count, 22 bytes each (padded to 4 when not compressed)
                at = 2 + 22 * struct.unpack_from(">H", data, 0)[0]
                data = data[at if size >> 31 else (at + 3) & ~3:]
            if packed:   # runs of data, or of padding: a size with the top bit set, then 68 bytes of seed
                out, p = bytearray(), 0
                while p < len(data) and len(out) < length:
                    n = struct.unpack_from(">I", data, p)[0]
                    p += 4
                    if n >> 31:
                        n &= 0x7FFFFFFF
                        p += 68
                        out += bytes(n)
                    else:
                        out += data[p:p + n]
                        p += n
                data = bytes(out)
        self.cached = (i, data)
        return data

    def read(self, offset: int, size: int) -> bytes:
        return self._partition(offset, size) if self.disc == 2 else self._disc(offset, size)

    def _partition(self, offset: int, size: int) -> bytes:
        """Wii game partition data by offset: 0x7C00 bytes of each 0x8000-byte sector, the hashes left out."""
        out = bytearray()
        per = self.chunk // 0x8000
        sector, within = divmod(offset, 0x7C00)
        while size > 0:
            first = self.partition[0]
            entry, k = (first, sector) if sector < first[1] else (self.partition[1], sector - first[1])
            data = self._group(entry[2] + k // per, per * 0x7C00, wii=True)
            piece = data[(k % per) * 0x7C00 + within:(k % per + 1) * 0x7C00][:size]
            if not piece:
                break
            out += piece
            size -= len(piece)
            sector, within = sector + 1, 0
        return bytes(out)

    def _disc(self, offset: int, size: int) -> bytes:
        out = bytearray()
        while size > 0:
            if offset < 0x80:
                piece = self.head[offset:offset + size]
            else:
                entry = next(e for e in self.raw if e[0] <= offset < e[0] + e[1])
                start = entry[0] - entry[0] % 0x8000
                k, within = divmod(offset - start, self.chunk)
                length = min(self.chunk, entry[0] + entry[1] - start - k * self.chunk)
                piece = self._group(entry[2] + k, length)[within:within + size]
            if not piece:
                break
            out += piece
            offset += len(piece)
            size -= len(piece)
        return bytes(out)


class Plain:
    """A whole disc image file read by offset."""

    def __init__(self, path: Path):
        self.f = path.open("rb")

    def read(self, offset: int, size: int) -> bytes:
        self.f.seek(offset)
        return self.f.read(size)


def is_gamecube(path: Path) -> bool:
    with path.open("rb") as f:
        f.seek(0x1C)
        return f.read(4) == b"\xc2\x33\x9f\x3d"


class GameCube:
    """Files of a GameCube disc (or a Wii game partition, whose offsets are stored divided by 4), by path, from the
    file table the disc header points to."""

    def __init__(self, disc):
        self.disc = disc
        self.game_id = disc.read(0, 6).decode("ascii", "replace")
        shift = 2 if getattr(disc, "disc", 1) == 2 else 0
        fst, size = (v << shift for v in struct.unpack(">II", disc.read(0x424, 8)))
        t = disc.read(fst, size)
        n = struct.unpack_from(">I", t, 8)[0]
        names = t[n * 12:]
        self.files: dict[str, tuple[int, int]] = {}
        stack = [(n, "")]
        for i in range(1, n):
            while i >= stack[-1][0]:
                stack.pop()
            word, offset, length = struct.unpack_from(">III", t, i * 12)
            if not word >> 24:
                offset <<= shift
            at = word & 0xFFFFFF
            name = stack[-1][1] + names[at:names.index(b"\0", at)].decode("cp932")
            if word >> 24:
                stack.append((length, name + "/"))
            else:
                self.files[name] = (offset, length)

    def read(self, name: str, offset: int = 0, size: int | None = None) -> bytes:
        start, length = self.files[name]
        return self.disc.read(start + offset, length - offset if size is None else size)


def dsp_decode(data: bytes) -> np.ndarray:
    """A standard DSP file (0x60-byte big-endian header, then 8-byte frames of 14 4-bit samples) -> int16."""
    samples = struct.unpack_from(">I", data, 0)[0]
    coefs = struct.unpack_from(">16h", data, 0x1C)
    h1, h2 = struct.unpack_from(">hh", data, 0x40)
    out = np.empty(samples, dtype=np.int16)
    body = data[0x60:]
    n = 0
    for at in range(0, len(body) - 7, 8):
        scale, c = 1 << (body[at] & 15), body[at] >> 4 & 7
        c1, c2 = coefs[c * 2], coefs[c * 2 + 1]
        for b in body[at + 1:at + 8]:
            for nib in (b >> 4, b & 15):
                if n == samples:
                    return out
                x = (((nib - 16 if nib > 7 else nib) * scale << 11) + 1024 + c1 * h1 + c2 * h2) >> 11
                x = -32768 if x < -32768 else 32767 if x > 32767 else x
                out[n] = x
                n += 1
                h2, h1 = h1, x
    return out[:n]


def adx_decode(data: bytes) -> np.ndarray:
    """CRI ADX (mono, 4-bit, 18-byte frames of a scale and 32 samples): the prediction from the header's high-pass
    frequency -> int16."""
    start = struct.unpack_from(">H", data, 2)[0] + 4
    frame = data[5]
    rate, samples = struct.unpack_from(">II", data, 8)
    highpass = struct.unpack_from(">H", data, 16)[0]
    a = math.sqrt(2) - math.cos(2 * math.pi * highpass / rate)
    b = math.sqrt(2) - 1
    c = (a - math.sqrt((a + b) * (a - b))) / b
    c1, c2 = int(c * 2 * 4096), int(-(c * c) * 4096)
    out = np.empty(samples, dtype=np.int16)
    h1 = h2 = n = 0
    for at in range(start, len(data) - frame + 1, frame):
        scale = struct.unpack_from(">H", data, at)[0]
        if scale & 0x8000:   # the end marker
            break
        for byte in data[at + 2:at + frame]:
            for nib in (byte >> 4, byte & 15):
                if n == samples:
                    return out
                x = (nib - 16 if nib > 7 else nib) * scale + ((c1 * h1 + c2 * h2) >> 12)
                x = -32768 if x < -32768 else 32767 if x > 32767 else x
                out[n] = x
                n += 1
                h2, h1 = h1, x
    return out[:n]

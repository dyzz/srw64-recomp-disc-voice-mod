"""PS1 discs for the voice tools: raw 2352-byte images (bin/cue, img, raw .iso) and XA ADPCM audio.

A PS1 game's voices are XA audio in Mode 2 Form 2 sectors (2324 bytes each). Only an image that keeps whole
2352-byte sectors has them; a 2048-byte .iso keeps Form 1 data only (docs/design.md §3.1).
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

RAW = 2352
SYNC = b'\x00' + b'\xff' * 10 + b'\x00'
XA_RATE = {0: 37800, 1: 18900}


def is_raw(path: Path) -> bool:
    """Whole 2352-byte sectors: the size divides and sector 16 (the volume descriptor) starts with the sync."""
    size = path.stat().st_size
    if size % RAW:
        return False
    with path.open('rb') as f:
        f.seek(16 * RAW)
        return f.read(12) == SYNC


def bin_of_cue(cue: Path) -> Path:
    """The data track's file of a cue sheet (track 1, MODE2/2352 or MODE1/2352)."""
    for line in cue.read_text(errors='replace').splitlines():
        line = line.strip()
        if line.upper().startswith('FILE'):
            name = line[line.index('"') + 1:line.rindex('"')] if '"' in line else line.split()[1]
            return cue.parent / name
    raise ValueError(f'{cue}: no FILE line')


class RawImage:
    """Root-directory files of a raw 2352-byte image, read as Form 1 data or as whole sectors."""

    def __init__(self, path: Path):
        self.path = path
        self.f = path.open('rb')
        pvd = self.data(16)
        if pvd[1:6] != b'CD001':
            raise ValueError(f'{path}: not an ISO 9660 disc')
        root = pvd[156:190]
        extent, size = struct.unpack_from('<I', root, 2)[0], struct.unpack_from('<I', root, 10)[0]
        self.files: dict[str, tuple[int, int]] = {}   # name -> (first sector, size in bytes)
        buf = b''.join(self.data(extent + i) for i in range((size + 2047) // 2048))
        pos = 0
        while pos < size:
            n = buf[pos]
            if n == 0:
                pos = (pos // 2048 + 1) * 2048
                continue
            rec = buf[pos:pos + n]
            name = rec[33:33 + rec[32]].decode('ascii', 'replace').split(';')[0]
            if not rec[25] & 2:
                self.files[name.upper()] = (struct.unpack_from('<I', rec, 2)[0], struct.unpack_from('<I', rec, 10)[0])
            pos += n
        self.subdirs = {}

    def raw(self, lba: int) -> bytes:
        self.f.seek(lba * RAW)
        return self.f.read(RAW)

    def data(self, lba: int) -> bytes:
        return self.raw(lba)[24:24 + 2048]

    def entry(self, name: str) -> tuple[int, int]:
        """(first sector, size) of a file, also one path deep ('XA/TEST.XA')."""
        name = name.upper()
        if name in self.files:
            return self.files[name]
        folder, _, leaf = name.partition('/')
        if folder not in self.subdirs:
            lba, size = self._dir_of(folder)
            self.subdirs[folder] = self._list(lba, size)
        return self.subdirs[folder][leaf]

    def _dir_of(self, folder: str) -> tuple[int, int]:
        pvd = self.data(16)
        root = pvd[156:190]
        for name, (lba, size, is_dir) in self._list(struct.unpack_from('<I', root, 2)[0], struct.unpack_from('<I', root, 10)[0], dirs=True).items():
            if is_dir and name == folder:
                return lba, size
        raise KeyError(folder)

    def _list(self, extent: int, size: int, dirs: bool = False) -> dict:
        buf = b''.join(self.data(extent + i) for i in range((size + 2047) // 2048))
        out, pos = {}, 0
        while pos < size:
            n = buf[pos]
            if n == 0:
                pos = (pos // 2048 + 1) * 2048
                continue
            rec = buf[pos:pos + n]
            name = rec[33:33 + rec[32]]
            if name not in (b'\0', b'\1'):
                nm = name.decode('ascii', 'replace').split(';')[0].upper()
                lba, sz = struct.unpack_from('<I', rec, 2)[0], struct.unpack_from('<I', rec, 10)[0]
                out[nm] = (lba, sz, bool(rec[25] & 2)) if dirs else (lba, sz)
            pos += n
        return out

    def read(self, name: str, offset: int = 0, size: int | None = None) -> bytes:
        """Form 1 bytes of a file."""
        lba, length = self.entry(name)
        size = length - offset if size is None else size
        first, skip = divmod(offset, 2048)
        need = (skip + size + 2047) // 2048
        return b''.join(self.data(lba + first + i) for i in range(need))[skip:skip + size]


K0 = (0, 60, 115, 98)
K1 = (0, 0, -52, -55)


def xa_decode(payloads: list[bytes]) -> np.ndarray:
    """4-bit mono XA ADPCM sectors (2304-byte payloads: 18 groups of 128 bytes, 8 units of 28 samples) -> int16."""
    out = np.empty(len(payloads) * 18 * 8 * 28, dtype=np.int16)
    n = 0
    h1 = h2 = 0
    for sec in payloads:
        b = np.frombuffer(sec, dtype=np.uint8)
        for g in range(18):
            grp = b[g * 128:(g + 1) * 128]
            for u in range(8):
                hdr = int(grp[4 + u])
                shift, filt = hdr & 15, min(hdr >> 4, 3)
                data = grp[16 + (u >> 1)::4][:28]
                nib = (data >> 4) if (u & 1) else (data & 15)
                raw = ((nib.astype(np.int32) << 12).astype(np.int16).astype(np.int32)) >> shift
                k0, k1 = K0[filt], K1[filt]
                for v in raw.tolist():
                    x = v + ((h1 * k0 + h2 * k1 + 32) >> 6)
                    x = -32768 if x < -32768 else 32767 if x > 32767 else x
                    out[n] = x
                    n += 1
                    h2, h1 = h1, x
    return out[:n]


SPU_K0 = (0, 60, 115, 98, 122)
SPU_K1 = (0, 0, -52, -55, -60)


def spu_decode(data: bytes) -> np.ndarray:
    """Sony SPU ADPCM (PS2 VAG data, no header): 16-byte blocks of a shift/filter byte, a flag byte and 28 4-bit
    samples -> int16."""
    b = np.frombuffer(data[:len(data) // 16 * 16], dtype=np.uint8).reshape(-1, 16)
    out = np.empty(len(b) * 28, dtype=np.int16)
    n = 0
    h1 = h2 = 0
    for blk in b:
        shift, filt = int(blk[0]) & 15, min(int(blk[0]) >> 4, 4)
        nib = np.empty(28, dtype=np.int32)
        nib[0::2], nib[1::2] = blk[2:] & 15, blk[2:] >> 4
        raw = ((nib << 12).astype(np.int16).astype(np.int32)) >> (shift if shift <= 12 else 9)
        k0, k1 = SPU_K0[filt], SPU_K1[filt]
        for v in raw.tolist():
            x = v + ((h1 * k0 + h2 * k1 + 32) >> 6)
            x = -32768 if x < -32768 else 32767 if x > 32767 else x
            out[n] = x
            n += 1
            h2, h1 = h1, x
    return out[:n]


class GroupTable:
    """A voice table in groups (F完結編): 6-byte entries (number, channel, 18-bit start sector, length in the channel's
    sectors); u16 group starts after a count. Voice v is entry number v & 127 of group v >> 7. コンプリートボックス's
    entries are 5 bytes, the length without its high byte."""

    def __init__(self, entries: bytes, groups: bytes, size: int = 6):
        self.E = [(e[0], e[1], e[2] | e[3] << 8 | (e[4] & 3) << 16, e[4] >> 2 | (e[5] << 6 if size == 6 else 0))
                  for e in (entries[i:i + size] for i in range(0, len(entries) - size + 1, size))]
        self.G = struct.unpack(f'<{len(groups) // 2}H', groups)

    def find(self, v: int):
        k, n = v >> 7, v & 127
        if not 0 < k < len(self.G) - 1:
            return None
        return next((e for e in self.E[self.G[k]:self.G[k + 1]] if e[0] == n), None)

    def sectors(self, v: int) -> list[int]:
        """File-relative sectors of voice v: every 32nd from its start (its channel's)."""
        e = self.find(v)
        return [] if e is None else [e[2] + 32 * j for j in range(e[3])]


class StreamTable:
    """新's voices: speaker p = v >> 8 says line n = (v - 1) & 127 from one stream, a channel of one of the 16-channel
    XA files: byte p of the stream table is file << 4 | channel; the file's channel has a u16 position table (in its
    channel's sectors, through a pointer table of 8 x 16 RAM addresses), line n running from position n to n + 1."""

    def __init__(self, exe: bytes, streams: int, pointers: int, load: int = 0x8002F800):
        self.exe, self.load = exe, load
        self.S = exe[streams:streams + 256]
        self.P = struct.unpack_from('<128I', exe, pointers)

    def find(self, v: int):
        """(file number, [file-relative sectors]) of voice v, or None."""
        p, n = v >> 8, (v - 1) & 127
        f, c = self.S[p] >> 4, self.S[p] & 15
        at = self.P[f * 16 + c] - self.load + 2 * n
        if not 0 <= at < len(self.exe) - 4:
            return None
        a, b = struct.unpack_from('<2H', self.exe, at)
        return (f, [k * 16 + c for k in range(a, b)]) if 0 < b - a < 2000 else None


def lz_decompress(b: bytes) -> bytes:
    """第4次S's LZ (SLPS_001.96 0x800C345C): flag bits high first from flag bytes; 1 = a literal byte; 01 = a 13-bit
    back offset and a 3-bit length (+2; 0: the next byte n, 0 ends, else n + 1); 00 = two bits of length (+2) and an
    8-bit back offset."""
    out, i, flags, left = bytearray(), 0, 0, 0

    def bit() -> int:
        nonlocal flags, left, i
        if left == 0:
            flags, left = b[i], 8
            i += 1
        left -= 1
        return (flags >> left) & 1

    while True:
        if bit():
            out.append(b[i])
            i += 1
            continue
        if bit():
            w = b[i] << 8 | b[i + 1]
            i += 2
            back, n = (w >> 3) - 0x2000, w & 7
            if n:
                n += 2
            else:
                n = b[i]
                i += 1
                if n == 0:
                    return bytes(out)
                n += 1
        else:
            n = (bit() << 1 | bit()) + 2
            back = b[i] - 0x100
            i += 1
        p = len(out) + back
        for k in range(n):
            out.append(out[p + k])


class OwnerTable:
    """第4次S's voices, from its battle overlay (loaded at `load`): speaker p = (v >> 8) & 0x7f, line n = v & 0xff;
    p's 3 bytes at `owners` are (XA file, channel, volume); u32 `tables` + 4 * file points to 16 channel pointers,
    each a u16 table of file sectors: line n from entry n to n + 1, the channel's every 16th sector."""

    def __init__(self, overlay: bytes, load: int, owners: int, tables: int):
        self.b, self.load, self.owners, self.tables = overlay, load, owners, tables

    def _u32(self, ram: int) -> int:
        return struct.unpack_from('<I', self.b, ram - self.load)[0]

    def find(self, v: int):
        """(file number, [file-relative sectors]) of voice v, or None."""
        p, n = (v >> 8) & 0x7F, v & 0xFF
        f, c = self.b[self.owners - self.load + 3 * p], self.b[self.owners - self.load + 3 * p + 1]
        if f > 2:
            return None
        at = self._u32(self._u32(self.tables + 4 * f) + 4 * c) - self.load + 2 * n
        a, e = struct.unpack_from('<2H', self.b, at)
        return (f, [s for s in range(a, e) if s % 16 == c]) if 0 < e - a < 4000 else None

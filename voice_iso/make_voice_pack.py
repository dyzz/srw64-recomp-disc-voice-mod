#!/usr/bin/env python3
"""Makes a battle voice MOD package for SRW64 (MARCHWIND 64) from the player's own disc images.

    python3 voice_iso/make_voice_pack.py "Super Robot Taisen Impact (Japan, Asia).iso" \
        "Super Robot Taisen Alpha (Japan).cue" -o out

Reads each image (.iso; PS1 discs as .bin/.cue, .img or a raw 2352-byte .iso, whose XA voices a 2048-byte
.iso cannot hold; GameCube discs as .iso, .gcm or Dolphin's .rvz; .chd through MAME's chdman; ATRAC3plus voices need ffmpeg; a PSP game whose data is
encrypted needs the tools psp/build.sh builds), finds which game it is by the voice maps in
maps/, checks every voice segment it needs against the map's checksum, and writes
<out>/<id>-<version>.srw64mod with audio/voice/battle/<record>.ogg (Ogg Vorbis), every
line brought to the loudness of SRW64's own battle effects (clips.TARGET_DBFS, --loudness).
Several images make one package: a line goes to the image whose entry is not marked replaceable,
then the exact line over a near one, then the image given first.

Nothing from the images leaves this computer; the package is for the player's own use (no license,
so the game does not offer it for sharing). Needs numpy and soundfile (pip install numpy soundfile).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import clips  # noqa: E402
import gamecube  # noqa: E402
import psx  # noqa: E402

SECTOR = 2048
SCHEMA = "srw64.mod.v1"
MOD_ID = "srw64.battle-voices-disc"
VERSION = "1.0.0"
GAME = ">=0.5.2"
PSP_TOOLS = ROOT / "psp" / "bin"


class MissingTool(RuntimeError):
    """A program this image needs is not installed; said as it is, not as a wrong image."""


class Iso:
    """Files of an ISO 9660 image, by name at the root and by path below it ('PSP_GAME/INSDIR/DATA017.BIN')."""

    def __init__(self, path: Path):
        self.f = path.open("rb")
        pvd = self._read(16 * SECTOR, SECTOR)
        if pvd[1:6] != b"CD001":
            raise ValueError(f"{path}: not an ISO 9660 image")
        root = pvd[156:190]
        self.files: dict[str, tuple[int, int]] = {}
        self._walk(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], "", 0)

    def _walk(self, extent: int, size: int, prefix: str, depth: int) -> None:
        data, pos = self._read(extent * SECTOR, size), 0
        while pos < len(data):
            n = data[pos]
            if n == 0:   # records never cross a sector; the rest of this one is padding
                pos = (pos // SECTOR + 1) * SECTOR
                continue
            rec = data[pos:pos + n]
            raw = rec[33:33 + rec[32]]
            pos += n
            if raw in (b"\0", b"\1"):
                continue
            name = prefix + raw.decode("ascii", "replace").split(";")[0].upper()
            lba, length = struct.unpack_from("<I", rec, 2)[0], struct.unpack_from("<I", rec, 10)[0]
            if rec[25] & 2:
                if depth < 4:
                    self._walk(lba, length, name + "/", depth + 1)
            else:
                self.files[name] = (lba * SECTOR, length)

    def _read(self, offset: int, size: int) -> bytes:
        self.f.seek(offset)
        return self.f.read(size)

    def read(self, name: str, offset: int = 0, size: int | None = None) -> bytes:
        start, length = self.files[name.upper()]
        return self._read(start + offset, length - offset if size is None else size)


def psp_tool(name: str) -> str:
    tool = PSP_TOOLS / name
    if tool.exists():
        return str(tool)
    found = shutil.which(name)
    if not found:
        raise MissingTool(f"this disc's data is encrypted and needs {name}: run psp/build.sh first (see README)")
    return found


class Decrypted:
    """An image whose encrypted files (a PSP game's ~PSP executable, its PGD data files) read as plain copies
    made in scratch by pspdecrypt and pgd_decrypt (psp/build.sh); everything else reads from the image."""

    def __init__(self, img, scratch: Path):
        self.img, self.scratch, self.files, self.plain = img, scratch, img.files, {}

    def decrypt(self, name: str, kind: str) -> None:
        if name.upper() in self.plain:
            return
        stem = self.scratch / name.replace("/", "_")
        enc, out = stem.with_suffix(".enc"), stem.with_suffix(".dec")
        enc.write_bytes(self.img.read(name))
        command = ([psp_tool("pspdecrypt"), "-o", str(out), str(enc)] if kind == "~PSP"
                   else [psp_tool("pgd_decrypt"), str(enc), str(out)])
        done = subprocess.run(command, capture_output=True, text=True)
        enc.unlink()
        if done.returncode or not out.exists():
            raise ValueError(f"{name}: decryption failed ({(done.stderr or done.stdout).strip()[:200]})")
        self.plain[name.upper()] = out

    def read(self, name: str, offset: int = 0, size: int | None = None) -> bytes:
        plain = self.plain.get(name.upper())
        if plain is None:
            return self.img.read(name, offset, size)
        with plain.open("rb") as f:
            f.seek(offset)
            return f.read(-1 if size is None else size)


def open_image(path: Path, scratch: Path):
    """An image's root files: a 2048-byte ISO (PS2, PSP), or whole 2352-byte sectors (PS1: bin/cue, img,
    a raw .iso; a .chd is first turned back into one by MAME's chdman)."""
    suffix = path.suffix.lower()
    if suffix == ".rvz":
        return gamecube.GameCube(gamecube.Rvz(path))
    if suffix == ".cue":
        return psx.RawImage(psx.bin_of_cue(path))
    if suffix == ".chd":
        chdman = shutil.which("chdman")
        if not chdman:
            raise ValueError(f"{path.name}: a .chd needs MAME's chdman on the PATH")
        info = subprocess.run([chdman, "info", "-i", str(path)], capture_output=True, text=True).stdout
        cd = "CHCD" in info or "CHT2" in info or "CD-ROM" in info
        out = scratch / (path.stem + (".cue" if cd else ".iso"))
        print(f"  chdman: {path.name} -> {out.name}")
        subprocess.run([chdman, "extractcd" if cd else "extractdvd", "-i", str(path), "-o", str(out), "-f"],
                       check=True, capture_output=True)
        return open_image(out, scratch)
    if gamecube.is_gamecube(path):
        return gamecube.GameCube(gamecube.Plain(path))
    if psx.is_raw(path):
        return psx.RawImage(path)
    return Iso(path)


def boot_file(img) -> tuple[str, bool]:
    """The executable SYSTEM.CNF starts (a PSP disc: its PARAM.SFO, which holds the disc ID), and whether the disc
    is a PS1 one (BOOT, not PS2's BOOT2)."""
    if isinstance(img, gamecube.GameCube):
        return img.game_id.upper(), False
    if "PSP_GAME/PARAM.SFO" in getattr(img, "files", {}):
        return img.read("PSP_GAME/PARAM.SFO").decode("ascii", "replace").upper(), False
    cnf = img.read("SYSTEM.CNF").decode("ascii", "replace") if "SYSTEM.CNF" in img.files else ""
    ps1 = any(line.strip().upper().startswith("BOOT ") or line.strip().upper().startswith("BOOT=") for line in cnf.splitlines())
    return cnf.upper(), ps1


class Source:
    """One image matched to its voice map."""

    def __init__(self, img, vmap: dict, path: Path, scratch: Path):
        a = vmap["audio"]
        idx = a["index"]
        encrypted = [(f["file"], f["encrypted"]) for f in (a, idx) if f.get("encrypted")]
        if encrypted:   # 第2次Z破界篇: the executable holds the index, a PGD file the voices
            img = Decrypted(img, scratch)
            for name, kind in encrypted:
                img.decrypt(name, kind)
        self.img, self.map, self.path = img, vmap, path
        self.format, self.audio, self.rate = a["format"], a["file"], a["rate"]
        if "groups" not in idx and "streams" not in idx and "people" not in idx and "owners" not in idx and self.format not in ("at3p", "spu", "dsp"):
            self.index = np.frombuffer(img.read(idx["file"], idx["offset"], idx["entries"] * 4), dtype="<u4").astype(np.int64)
        if self.format == "s16le":
            self.unit = idx["unit"]
            if "people" in idx:   # MX: (offset from the table, count) per person, then 16-byte entries (sector, bytes, 1, 32767)
                head = np.frombuffer(img.read(idx["file"], idx["offset"], idx["people"] * 8), dtype="<u4").reshape(-1, 2)
                self.clips = {}   # clip = person * 1000 + line -> (byte offset, size)
                for p, (o, n) in enumerate(head.tolist()):
                    if o == 0xFFFFFFFF:
                        continue
                    t = np.frombuffer(img.read(idx["file"], idx["offset"] + o, n * 16), dtype="<u4").reshape(-1, 4)
                    for k, (sector, size, _, _) in enumerate(t.tolist()):
                        self.clips[p * 1000 + k] = (sector * self.unit, size)
        elif self.format == "at3p":   # ATRAC3plus clips (RIFF); the index holds byte offsets, one after another
            stride = idx.get("stride", 4)   # A PORTABLE: 16-byte entries (1, offset, size, ...)
            t = np.frombuffer(img.read(idx["file"], idx["offset"], idx["entries"] * stride), dtype="<u4").astype(np.int64)
            t = t.reshape(idx["entries"], stride // 4)
            self.offsets = t[:, 0] if stride == 4 else t[:, 1]
            self.sizes = np.diff(self.offsets) if stride == 4 else t[:, 2]
            if not shutil.which("ffmpeg"):
                raise ValueError(f"{path.name}: its voices are ATRAC3plus, which needs ffmpeg on the PATH")
        elif self.format == "spu":   # SPU ADPCM clips; 第3次α: 16-byte entries (size, 0, byte offset, rate), Z: (size, byte offset)
            stride = idx.get("stride", 16)
            t = np.frombuffer(img.read(idx["file"], idx["offset"], idx["entries"] * stride), dtype="<u4").astype(np.int64)
            t = t.reshape(idx["entries"], stride // 4)
            self.offsets, self.sizes = (t[:, 2] if stride == 16 else t[:, 1]), t[:, 0]
        elif self.format == "dsp":   # GC: big-endian (offset, size) per clip, each a DSP file with its header
            t = np.frombuffer(img.read(idx["file"], idx["offset"], idx["entries"] * 8), dtype=">u4").astype(np.int64).reshape(-1, 2)
            self.offsets, self.sizes = t[:, 0], t[:, 1]
        else:   # first sector of each XA file (新 spreads its voices over several)
            self.xa_lbas = [img.entry(f)[0] for f in a.get("files", [self.audio])]
        if "groups" in idx:   # F完結編 (6-byte entries), コンプリートボックス (5-byte), found through group starts
            size = idx.get("size", 6)
            self.table = psx.GroupTable(img.read(idx["file"], idx["offset"], idx["entries"] * size),
                                        img.read(idx["file"], idx["groups"]["offset"], idx["groups"]["count"] * 2), size)
        if "owners" in idx:   # 第4次S: the tables are in its compressed battle overlay
            self.owners = psx.OwnerTable(psx.lz_decompress(img.read(idx["file"])), idx["load"], idx["owners"], idx["tables"])
        if "streams" in idx:   # 新: a stream (file, channel) per voice owner, with position tables
            self.streams = psx.StreamTable(img.read(idx["file"]), idx["streams"], idx["pointers"])

    def _xa_sectors(self, v: int) -> list[bytes]:
        if hasattr(self, "owners"):
            f, fs = self.owners.find(v)
            return [self.img.raw(self.xa_lbas[f] + s)[24:24 + 2304] for s in fs]
        if hasattr(self, "streams"):
            f, fs = self.streams.find(v)
            return [self.img.raw(self.xa_lbas[f] + s)[24:24 + 2304] for s in fs]
        if hasattr(self, "table"):
            fs = self.table.sectors(v)
        else:   # Alpha: the table holds channel << 27 | flags | end sector, from the XA file's start
            t, p = self.index[v], self.index[v - 1]
            c, end = int(t >> 27), int(t & 0xFFFFFF) - 0x10
            start = int(p & 0xFFFFFF) if int(p >> 27) == c and v != 1 else 0
            fs = [f for f in range(start, end) if f % 32 == c]
        return [self.img.raw(self.xa_lbas[0] + f)[24:24 + 2304] for f in fs]

    def stored(self, n: int) -> bytes:
        """Segment n as stored on the disc (what the map's checksum covers)."""
        if self.format == "s16le" and hasattr(self, "clips"):
            return self.img.read(self.audio, *self.clips[n])
        if self.format == "s16le":
            start, end = self.index[n] * self.unit, self.index[n + 1] * self.unit
            return self.img.read(self.audio, int(start), int(end - start))
        if self.format in ("at3p", "spu", "dsp"):
            return self.img.read(self.audio, int(self.offsets[n]), int(self.sizes[n]))
        return b"".join(self._xa_sectors(n))

    def segment(self, n: int) -> np.ndarray:
        if self.format == "s16le":
            return np.frombuffer(self.stored(n), dtype="<i2")
        if self.format == "at3p":
            pcm = subprocess.run(["ffmpeg", "-v", "error", "-f", "wav", "-i", "pipe:0", "-ac", "1", "-ar", str(self.rate), "-f", "s16le", "pipe:1"],
                                 input=self.stored(n), capture_output=True, check=True).stdout
            return np.frombuffer(pcm, dtype="<i2")
        if self.format == "spu":
            return psx.spu_decode(self.stored(n))
        if self.format == "dsp":
            return gamecube.dsp_decode(self.stored(n))
        return psx.xa_decode(self._xa_sectors(n))

    def check(self, entry: dict) -> bool:
        return all(hashlib.sha1(self.stored(c["clip"])).hexdigest()[:len(c["sha1"])] == c["sha1"] for c in entry["clips"])


def identify(img, path: Path, maps: list[dict], scratch: Path) -> Source:
    """The map whose boot file the image starts and whose index reads back right."""
    cnf, ps1 = boot_file(img)
    for vmap in maps:
        boot = vmap.get("disc_id") or vmap["audio"]["index"]["file"]
        if boot.upper() not in cnf:
            continue
        if vmap["audio"]["format"] == "xa" and not isinstance(img, psx.RawImage):
            raise ValueError(f"{path.name}: {vmap['game']} keeps its voices in XA sectors, which a 2048-byte .iso "
                             "does not hold. Use a .bin/.cue (or .chd) image of the disc instead.")
        try:
            src = Source(img, vmap, path, scratch)
            ok = all(src.check(e) for e in list(vmap["lines"].values())[::200])
        except (KeyError, ValueError):
            ok = False
        if ok:
            return src
        raise ValueError(f"{path.name}: looks like {vmap['game']}, but its voice data differs from the version this map was made from")
    if ps1 and not isinstance(img, psx.RawImage):
        raise ValueError(f"{path.name}: a PS1 disc as a 2048-byte .iso. Its voices, if any, are not in this kind of image; "
                         "use a .bin/.cue (or .chd).")
    raise ValueError(f"{path.name}: not a game with a voice map in maps/")


def choose(sources: list[Source]) -> dict[int, tuple[Source, dict]]:
    """For each record, the source that voices it best."""
    best: dict[int, tuple[tuple, Source, dict]] = {}
    for order, src in enumerate(sources):
        for rec, e in src.map["lines"].items():
            rank = ("replaceable" in e, e["grade"], order)   # A, then B, then C
            if int(rec) not in best or rank < best[int(rec)][0]:
                best[int(rec)] = (rank, src, e)
    return {rec: (src, e) for rec, (_, src, e) in sorted(best.items())}


def ogg(a: np.ndarray, rate: int) -> bytes:
    import soundfile
    buf = io.BytesIO()
    soundfile.write(buf, a, rate, format="OGG", subtype="VORBIS", compression_level=0.5)
    return buf.getvalue()


def manifest(sources: list[Source]) -> dict:
    games = "、".join(s.map["game"] for s in sources)
    note = {
        "ja": f"プレイヤー自身のディスクイメージ（{games}）から作った戦闘ボイス。個人での利用に限ります。",
        "zh-Hans": f"用玩家自己的光盘镜像（{games}）生成的战斗语音，仅供个人使用。",
        "zh-Hant": f"用玩家自己的光碟映像（{games}）生成的戰鬥語音，僅供個人使用。",
        "en": f"Battle voices made from the player's own disc images ({games}). For personal use only.",
    }
    return {"schema": SCHEMA, "id": MOD_ID, "version": VERSION,
            "name": {"ja": "戦闘ボイス（ディスクから）", "zh-Hans": "战斗语音（来自光盘）", "zh-Hant": "戰鬥語音（來自光碟）",
                     "en": "Battle Voices (from discs)"},
            "description": note, "authors": ["SRW64"], "game": GAME}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("images", nargs="+", type=Path, help="disc images (.iso, .cue, .rvz or .chd), the preferred one first")
    parser.add_argument("-o", "--out", type=Path, default=ROOT / "out", help="where the package goes (default out/)")
    parser.add_argument("--loudness", type=float, default=clips.TARGET_DBFS,
                        help=f"spoken loudness of every line in dBFS (default {clips.TARGET_DBFS:g}, SRW64's loud battle effects)")
    parser.add_argument("--maps", type=Path, default=ROOT / "maps", help="voice maps (default maps/)")
    args = parser.parse_args(argv)
    maps = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(args.maps.glob("*.json"))]
    with tempfile.TemporaryDirectory() as tmp:
        sources = []
        for n, path in enumerate(args.images):
            print(f"{path.name}")
            scratch = Path(tmp) / str(n)
            scratch.mkdir()
            src = identify(open_image(path, scratch), path, maps, scratch)
            print(f"  {src.map['game']}: {len(src.map['lines'])} lines")
            sources.append(src)
        picked = choose(sources)
        args.out.mkdir(parents=True, exist_ok=True)
        archive = args.out / f"{MOD_ID}-{VERSION}.srw64mod"
        bad = 0
        # mod.json, then the lines in record order, all with one fixed date: the same discs give the same file.
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            def add(name: str, data: bytes) -> None:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
                z.writestr(info, data)
            add("mod.json", (json.dumps(manifest(sources), ensure_ascii=False, indent=2) + "\n").encode())
            for i, (rec, (src, e)) in enumerate(picked.items()):
                if not src.check(e):
                    bad += 1
                    continue
                a = clips.leveled(clips.line_sound(e["clips"], src.segment, src.rate), args.loudness, rate=src.rate)
                add(f"audio/voice/battle/{rec}.ogg", ogg(a, src.rate))
                if i % 500 == 0:
                    print(f"  {i}/{len(picked)}")
        if bad:
            print(f"  {bad} lines skipped: their voice data differs from the map")
    print(f"{archive} ({archive.stat().st_size / 1e6:.1f} MB, {len(picked) - bad} lines)")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError) as error:   # an image this tool cannot use: say why, no traceback
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)

<p align="center">
  <img src="https://raw.githubusercontent.com/dyzz/srw64-recomp/main/web/public/brand/title-en.webp" alt="MARCHWIND64" width="560">
</p>

<p align="center"><b>Battle voice MOD maker for <a href="https://github.com/dyzz/srw64-recomp">MARCHWIND 64 (srw64-recomp)</a></b></p>

<p align="center">English · <a href="README.zh-Hans.md">简体中文</a></p>

# MARCHWIND 64 Disc Voice MOD Maker

This is the official battle voice MOD tool of [srw64-recomp](https://github.com/dyzz/srw64-recomp), the MARCHWIND 64 project: a native port of Super Robot Taisen 64. The original game's battle lines were never voiced. This tool reads **your own** disc images of later, voiced Super Robot Taisen games, finds where the same character says the same line (or one with the same meaning), and builds a battle voice MOD (`.srw64mod`) that MARCHWIND 64 plays in battle.

This repository holds only the generator and the voice maps (which segment of which disc speaks each SRW64 line, with checksums to verify it). **It contains no voices and no game data.** The package you build is for your own use; please do not share it.

## Supported discs

| Game | Serial | Platform | Image | Lines |
|---|---|---|---|---:|
| Super Robot Taisen IMPACT | SLPS-25104 | PS2 | .iso | 4,610 |
| Super Robot Taisen Alpha | SLPS-02636 | PS1 | .bin/.cue, .chd | 3,640 |
| Super Robot Taisen A PORTABLE | ULJS-00143 | PSP | .iso (plus ffmpeg) | 3,205 |
| 3rd Super Robot Taisen Alpha | SLPS-25537 | PS2 | .iso | 2,592 |
| Super Robot Taisen GC | DOL-GRWJ-JPN | GameCube | .iso, .gcm, .rvz | 2,567 |
| 2nd Super Robot Taisen Alpha | SLPS-25228 | PS2 | .iso | 2,531 |
| Super Robot Taisen F Kanketsu-hen | SLPS-01924 | PS1 | .bin/.cue, .chd | 2,381 |
| Super Robot Taisen Complete Box (Disc 1) | SLPS-02070 | PS1 | .bin/.cue, .chd | 2,309 |
| Super Robot Taisen MX | SLPS-25345 | PS2 | .iso | 2,097 |
| Super Robot Taisen Z | SLPS-25887, SLPS-73270 (The Best) | PS2 | .iso | 1,677 |
| Shin Super Robot Taisen | SLPS-00550 | PS1 | .bin/.cue, .chd | 1,514 |
| 2nd Super Robot Taisen Z Hakai-hen | ULJS-00379 | PSP | .iso (plus ffmpeg and the decryption tools) | 571 |

- The discs overlap a lot: all twelve together make about 7,870 lines. Any one disc works on its own.
- PS1 voices are in XA sectors, so a PS1 image must keep 2352-byte sectors (.bin/.cue, .img, a raw .iso or .chd). A 2048-byte .iso has no voices; the tool says so.
- Dolphin's .rvz is read directly (zstandard, in `requirements.txt`). A .chd needs MAME's `chdman` on the PATH. The two PSP discs' ATRAC3plus voices need `ffmpeg`.
- Z's original release and its PlayStation 2 the Best reprint each have a map; the Best changed five of the clips, so their lines are only in the original's map.
- An image must be the release the map was made from. Every segment is checked against its checksum, and lines that differ are skipped.

The original characters (Ark, Selain, Brad, Manami and the others) are on none of these discs. They have a separate AI voice package on [MARCHWIND 64's MOD page](https://srw64.dreamquest.club/en/mods/), which works together with the package built here.

## Coverage

SRW64 has 11,359 battle lines that can appear in play. All twelve discs together voice **7,878 of them (69%)**. Adding the original characters' AI voice package (843 lines) brings it to **8,721 (77%)**.

By series, with all twelve discs (the 846 lines of the original characters are left out; the AI package covers 843 of them):

| Series | Lines | Voiced | Coverage |
|---|---:|---:|---:|
| Mobile Suit Gundam Wing | 1,267 | 783 | 62% |
| Mobile Fighter G Gundam | 958 | 685 | 72% |
| Mobile Suit Zeta Gundam | 944 | 877 | 93% |
| Mobile Suit Gundam ZZ | 932 | 596 | 64% |
| Aura Battler Dunbine | 776 | 587 | 76% |
| UFO Robot Grendizer | 667 | 440 | 66% |
| Mazinger Z | 609 | 520 | 85% |
| Char's Counterattack | 607 | 575 | 95% |
| Blue Comet SPT Layzner | 599 | 536 | 89% |
| Dancouga: Super Beast Machine God | 543 | 498 | 92% |
| Great Mazinger | 501 | 289 | 58% |
| Six God Combination God Mars | 325 | 118 | 36% |
| Getter Robo G | 256 | 141 | 55% |
| Generic soldiers and others | 251 | 188 | 75% |
| Super Electromagnetic Robot Combattler V | 227 | 221 | 97% |
| Getter Robo | 212 | 184 | 87% |
| Giant Robo | 203 | 80 | 39% |
| Invincible Super Man Zambot 3 | 130 | 118 | 91% |
| Mobile Suit Gundam F91 | 100 | 77 | 77% |
| Mobile Suit Gundam 0083 | 96 | 87 | 91% |
| The 08th MS Team | 85 | 85 | 100% |
| Mobile Suit Gundam | 85 | 81 | 95% |
| Sengoku Majin GoShogun | 77 | 49 | 64% |
| Invincible Steel Man Daitarn 3 | 63 | 63 | 100% |

The biggest gaps are characters these discs never recorded, or whose lines are worded differently from SRW64's: GodMars, Giant Robo, Getter Robo G, Great Mazinger and Grendizer.

## You don't need every disc

Each disc's map was made against all of SRW64's lines on its own and does not depend on the others. One disc alone gives the lines in the table above. Several give their union, with the best segment picked for each line.

To get the most lines from the fewest discs, look for them in this order:

| Order | Disc | New lines | Total |
|---:|---|---:|---:|
| 1 | IMPACT | 4,610 | 4,610 |
| 2 | A PORTABLE | 1,155 | 5,765 |
| 3 | GC | 714 | 6,479 |
| 4 | Alpha | 494 | 6,973 |
| 5 | Shin | 238 | 7,211 |
| 6 | Z | 231 | 7,442 |
| 7 | F Kanketsu-hen | 127 | 7,569 |
| 8 | 3rd Alpha | 102 | 7,671 |
| 9 | 2nd Z Hakai-hen | 89 | 7,760 |
| 10 | MX | 64 | 7,824 |
| 11 | Complete Box | 35 | 7,859 |
| 12 | 2nd Alpha | 19 | 7,878 |

The first four already give nearly 90% of the total. The later ones mostly fill in a few characters: GC brings Layzner and Dancouga, Z brings Grendizer, 2nd Z Hakai-hen brings GodMars, and MX adds Kiral.

## Usage

Needs Python 3.10 or later:

```bash
pip install -r requirements.txt
python3 voice_iso/make_voice_pack.py "Super Robot Taisen Impact (Japan, Asia).iso" "Super Robot Taisen Alpha (Japan).cue"
```

Several discs make one package. When more than one disc has a line, the exact line wins over a near one, then the disc given first. All twelve take a few minutes.

The result is `out/srw64.battle-voices-disc-1.0.0.srw64mod` (about 145 MB for all twelve). Install it from the game's MOD page; it needs MARCHWIND 64 0.5.2 or later.

Options:

- `-o DIR`: where the package goes (default `out/`).
- `--loudness -15`: spoken loudness of every line in dBFS; the default matches the game's loud battle effects. The game's settings also have a voice volume.

### 2nd Z Hakai-hen: install the decryption tools first

This disc's program and data are encrypted. Run this once:

```bash
sh psp/build.sh
```

It downloads and builds [pspdecrypt](https://github.com/John-K/pspdecrypt) (GPL-3.0), leaving `pspdecrypt` and `pgd_decrypt` in `psp/bin/`. After that, run the generator as usual. It decrypts the two files it needs into a temporary folder and deletes them when done.

Building needs git, make, a C/C++ compiler, zlib and OpenSSL:

- macOS: the Xcode command line tools, plus `brew install openssl`
- Debian/Ubuntu: `build-essential zlib1g-dev libssl-dev`
- Windows: run it inside WSL or MSYS2

This repository has no keys or decryption algorithm of its own. It has only `psp/pgd_decrypt.c`, a small program that calls pspdecrypt's own library.

## Voice map format

`maps/<game>.json` starts with how to recognize the disc and where its voices are (`audio`). `lines` lists SRW64's battle line records (5799–17346):

- `clips`: the segments to play, joined in order. Each segment's `sha1` is the first 16 hex digits of the SHA-1 of its stored bytes. `part`, `weights` and `cut` take one piece of a segment, cut at its pauses.
- `grade`: A is the exact line, B a near line, C a shout or a line with the same meaning standing in.
- `replaceable`: another disc's exact line wins over this one.

## License

GPL-3.0-or-later.

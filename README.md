[English](README.en.md)

# srw64-recomp-disc-voices：光盘战斗语音生成器

[srw64-recomp](https://github.com/dyzz/srw64-recomp) 的配套工具。

[MARCHWIND 64](https://github.com/dyzz/srw64-recomp)（超级机器人大战 64 的原生移植）的战斗台词原本没有语音。这个工具读**你自己的**光盘镜像，从后来几作有语音的超级机器人大战里，把同一个角色说同一句（或意思相同的一句）的语音找出来，生成一个战斗语音 MOD（`.srw64mod`），装进游戏后战斗时会播放。

仓库里只有生成程序和对照表（哪句 64 台词用哪张盘的哪段语音，以及核对用的校验值），**不含任何语音或游戏数据**。生成的包只供你自己使用，请不要分发。

## 支持的光盘

| 游戏 | 编号 | 平台 | 镜像 | 句数 |
|---|---|---|---|---:|
| スーパーロボット大戦IMPACT | SLPS-25104 | PS2 | .iso | 4,610 |
| スーパーロボット大戦α | SLPS-02636 | PS1 | .bin/.cue、.chd | 3,640 |
| スーパーロボット大戦A PORTABLE | ULJS-00143 | PSP | .iso（另需 ffmpeg） | 3,205 |
| 第3次スーパーロボット大戦α | SLPS-25537 | PS2 | .iso | 2,592 |
| 第2次スーパーロボット大戦α | SLPS-25228 | PS2 | .iso | 2,531 |
| スーパーロボット大戦F完結編 | SLPS-01924 | PS1 | .bin/.cue、.chd | 2,381 |
| スーパーロボット大戦 コンプリートボックス（Disc 1） | SLPS-02070 | PS1 | .bin/.cue、.chd | 2,309 |
| スーパーロボット大戦MX | SLPS-25345 | PS2 | .iso | 2,097 |
| 新スーパーロボット大戦 | SLPS-00550 | PS1 | .bin/.cue、.chd | 1,514 |
| 第2次スーパーロボット大戦Z 破界篇 | ULJS-00379 | PSP | .iso（另需 ffmpeg 和解密工具） | 571 |

- 几张盘的句子有很多重叠，十张都给时合成约 7,380 句。只有一张也能用。
- PS1 的语音在 XA 扇区里，必须用 2352 字节扇区的镜像（.bin/.cue、.img、原始 .iso 或 .chd）。只有 2048 字节扇区的 .iso 没有语音，工具会提示。
- .chd 需要 MAME 的 `chdman` 在 PATH 里。两张 PSP 盘的 ATRAC3plus 语音需要 `ffmpeg`。
- 镜像要和做对照表的那一版一致。工具会逐段核对校验值，对不上的句子跳过。

原创人物（阿克、塞蕾茵、布拉德、玛娜米等）不在这些光盘里。他们的语音另有一个 AI 语音包，在 [MARCHWIND 64 的 MOD 页](https://srw64.dreamquest.club/zh/mods/)，可以和这里生成的包同时装。

## 没有全部光盘时

不用凑齐。每张盘的对照表都是单独对 64 全部台词做的，不依赖别的盘：只给一张，就有上表那么多句；给几张，就取它们的并集，同一句再挑最好的那段。

想用最少的盘得到最多的句子，可以按这个顺序找（括号里是加上这张后新增的句数）：

| 顺序 | 光盘 | 新增 | 累计 |
|---:|---|---:|---:|
| 1 | IMPACT | 4,610 | 4,610 |
| 2 | A PORTABLE | 1,155 | 5,765 |
| 3 | α | 615 | 6,380 |
| 4 | 新 | 378 | 6,758 |
| 5 | 第3次α | 254 | 7,012 |
| 6 | F完結編 | 149 | 7,161 |
| 7 | 第2次Z破界篇 | 90 | 7,251 |
| 8 | MX | 70 | 7,321 |
| 9 | コンプリートボックス | 41 | 7,362 |
| 10 | 第2次α | 19 | 7,381 |

前四张就有全部的九成以上。后面几张主要补个别人物，例如 第2次Z破界篇 补的几乎都是ゴッドマーズ，MX 补キラル。

## 用法

需要 Python 3.10 以上：

```bash
pip install -r requirements.txt
python3 voice_iso/make_voice_pack.py "Super Robot Taisen Impact (Japan, Asia).iso" "Super Robot Taisen Alpha (Japan).cue"
```

一次可以给多张盘，合成一个包。同一句几张盘都有时，优先用原句一致的那张，再按给出的先后。十张大约两三分钟。

结果在 `out/srw64.battle-voices-disc-1.0.0.srw64mod`，十张约 135 MB。在游戏的 MOD 页安装这个文件即可，需要 MARCHWIND 64 0.5.2 以上。

常用参数：

- `-o 目录`：输出位置，默认 `out/`。
- `--loudness -15`：每句说话部分的响度（dBFS），默认和游戏里较响的战斗音效持平。游戏设置里还可以单独调语音音量。

### 第2次Z破界篇：先装解密工具

这张盘的程序和数据是加密的。先运行一次：

```bash
sh psp/build.sh
```

它会下载并编译 [pspdecrypt](https://github.com/John-K/pspdecrypt)（GPL-3.0），在 `psp/bin/` 里生成 `pspdecrypt` 和 `pgd_decrypt`。之后正常运行生成器，它会把需要的两个文件解密到临时目录再读取，用完即删。

编译需要 git、make、C/C++ 编译器、zlib 和 OpenSSL：

- macOS：Xcode 命令行工具，加上 `brew install openssl`
- Debian/Ubuntu：`build-essential zlib1g-dev libssl-dev`
- Windows：在 WSL 或 MSYS2 里运行

本仓库没有密钥或解密算法，只有一个调用 pspdecrypt 自带库的小程序 `psp/pgd_decrypt.c`。

## 对照表格式

`maps/<游戏>.json` 开头写这张盘的识别信息和语音存放方式（`audio`），`lines` 按 64 的台词记录号（5799–17346）列出：

- `clips`：用哪几段语音，依次相接。每段的 `sha1` 是盘上原始数据 SHA-1 的前 16 位。`part`、`weights`、`cut` 表示只取这段里的一部分（按停顿切）。
- `grade`：A 原句一致，B 近句，C 喊声或同意思替代。
- `replaceable`：别的盘有原句时让给它。

## 许可证

GPL-3.0-or-later。

#!/bin/sh
# Builds the two programs a PSP disc with encrypted data needs (第2次スーパーロボット大戦Z 破界篇) into psp/bin/:
# pspdecrypt for its executable, and pgd_decrypt for its PGD data files. Both come from John-K/pspdecrypt
# (GPL-3.0), which this downloads; this repository carries no keys or decryption code of its own.
# Needs git, make, a C/C++ compiler, zlib and OpenSSL's libcrypto (macOS: Xcode command line tools and
# `brew install openssl`; Debian/Ubuntu: build-essential zlib1g-dev libssl-dev; Windows: inside WSL or MSYS2).
set -e
cd "$(dirname "$0")"
REV=c156627db7634d395c380c0a9589130f603307fc   # pspdecrypt 1.0, 2024-06-07

[ -d pspdecrypt ] || git clone https://github.com/John-K/pspdecrypt.git
git -C pspdecrypt checkout -q "$REV"

# OpenSSL from Homebrew is outside the compiler's default paths.
SSL=""
if command -v brew >/dev/null 2>&1 && brew --prefix openssl >/dev/null 2>&1; then
    P=$(brew --prefix openssl)
    SSL="-I$P/include -L$P/lib"
fi

make -C pspdecrypt CC="${CC:-cc} $SSL" CXX="${CXX:-c++} $SSL" EXTRA_FLAG="$SSL"
mkdir -p bin
cp pspdecrypt/pspdecrypt bin/
K=pspdecrypt/libkirk
${CC:-cc} -O2 -I"$K" $SSL -o bin/pgd_decrypt pgd_decrypt.c \
    "$K/AES.o" "$K/SHA1.o" "$K/amctrl.o" "$K/bn.o" "$K/ec.o" "$K/kirk_engine.o" -lz -lcrypto
echo "built: $(pwd)/bin/pspdecrypt $(pwd)/bin/pgd_decrypt"

/* pgd_decrypt <in> <out>: a PSP PGD file (a UMD game's encrypted data) decrypted with the key its own MAC
 * gives, through libkirk's amctrl from pspdecrypt (https://github.com/John-K/pspdecrypt). psp/build.sh builds it;
 * make_voice_pack.py runs it on the voice files of 第2次スーパーロボット大戦Z 破界篇.
 * SPDX-License-Identifier: GPL-3.0-or-later */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "kirk_engine.h"
#include "amctrl.h"

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: pgd_decrypt <in> <out>\n");
        return 2;
    }
    FILE *f = fopen(argv[1], "rb");
    if (!f) {
        perror(argv[1]);
        return 1;
    }
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    u8 *buf = malloc(n);
    if (!buf || fread(buf, 1, n, f) != (size_t)n) {
        fprintf(stderr, "%s: cannot read\n", argv[1]);
        return 1;
    }
    fclose(f);
    kirk_init();
    PGD_DESC *pgd = NULL;
    for (int flag = 2; flag >= 1 && !pgd; flag--)   /* the two MAC kinds a game's data uses */
        pgd = pgd_open(buf, flag, NULL);
    if (!pgd) {
        fprintf(stderr, "%s: not a PGD file this can open\n", argv[1]);
        return 1;
    }
    FILE *o = fopen(argv[2], "wb");
    if (!o) {
        perror(argv[2]);
        return 1;
    }
    u32 left = pgd->data_size;
    for (u32 b = 0; b < pgd->block_nr; b++) {
        memcpy(pgd->block_buf, buf + pgd->data_offset + b * pgd->block_size, pgd->block_size);
        pgd_decrypt_block(pgd, b);
        u32 k = left < pgd->block_size ? left : pgd->block_size;
        fwrite(pgd->block_buf, 1, k, o);
        left -= k;
    }
    fclose(o);
    pgd_close(pgd);
    free(buf);
    return 0;
}

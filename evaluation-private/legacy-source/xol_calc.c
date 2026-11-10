/*
 * xol_calc.c  --  Synthetic legacy "excess-of-loss" claims-recovery calculator.
 *
 * THIS FILE IS EVALUATION-AUTHORITY ONLY.
 * It is the original source for the synthetic legacy executable that the
 * DevSecOops investigation agents must analyse *blind* (compiled binary only).
 * It MUST NOT be mounted into, or made readable by, any investigation/runner
 * container, model tool scope, or sandbox profile.
 *
 * Treaty modelled (per-occurrence excess-of-loss, single layer):
 *     recovery = min( max(eligible_loss - attachment, 0), limit )
 *
 * Hidden treaty terms (compiled in as immediates so they are discoverable only
 * through black-box behaviour, not from a config file):
 *     attachment = $100,000.00
 *     limit      = $500,000.00
 *     currency   = USD, settled to the cent.
 *
 * Input  (stdin or file arg): CSV with header `claim_id,eligible_loss`
 *        eligible_loss is decimal dollars, e.g. 123456.78
 * Output (stdout): CSV with header `claim_id,recovery`
 *
 * ---------------------------------------------------------------------------
 * SEEDED DEFECT (OOPS-001)  --  do NOT disclose to investigation agents.
 *   Monetary amounts are scaled to integer cents using a 32-bit `int`.
 *   max int32 cents = 2,147,483,647 == $21,474,836.47.
 *   For eligible_loss above that, `(int)(dollars*100)` overflows and wraps,
 *   producing a wrong (often negative) recovery instead of the correct $500,000
 *   limit cap. Normal-range claims (<= ~$21.47M eligible) are computed exactly,
 *   so the correct business rule is still recoverable by black-box inference;
 *   only large claims reveal the defect.
 * ---------------------------------------------------------------------------
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Hidden treaty terms, in whole cents. */
#define ATTACHMENT_CENTS 10000000   /* $100,000.00 */
#define LIMIT_CENTS      50000000   /* $500,000.00 */

/* Round-half-up conversion of a decimal-dollar string to cents.
 * Returns value in `int` cents -- the seeded 32-bit container (OOPS-001). */
static int dollars_to_cents(const char *s) {
    double d = atof(s);
    /* half-up rounding on the cent, then narrowed to 32-bit int on return */
    double scaled = d * 100.0;
    long long cents = (long long)(scaled + (scaled >= 0 ? 0.5 : -0.5));
    return (int)cents;   /* <-- OOPS-001: silent 32-bit truncation/overflow */
}

static int xol_recovery(int eligible_cents) {
    int excess = eligible_cents - ATTACHMENT_CENTS;
    if (excess < 0) excess = 0;
    if (excess > LIMIT_CENTS) excess = LIMIT_CENTS;
    return excess;
}

int main(int argc, char **argv) {
    FILE *in = stdin;
    if (argc > 1) {
        in = fopen(argv[1], "r");
        if (!in) { fprintf(stderr, "cannot open input: %s\n", argv[1]); return 2; }
    }

    char line[512];
    int lineno = 0;
    printf("claim_id,recovery\n");
    while (fgets(line, sizeof(line), in)) {
        lineno++;
        /* strip newline */
        line[strcspn(line, "\r\n")] = 0;
        if (line[0] == 0) continue;
        /* skip header */
        if (lineno == 1 && strstr(line, "claim_id")) continue;

        char *comma = strchr(line, ',');
        if (!comma) { fprintf(stderr, "malformed row %d: %s\n", lineno, line); continue; }
        *comma = 0;
        const char *claim_id = line;
        const char *loss_str = comma + 1;

        int eligible_cents = dollars_to_cents(loss_str);
        int rec_cents = xol_recovery(eligible_cents);
        printf("%s,%d.%02d\n", claim_id, rec_cents / 100, abs(rec_cents % 100));
    }

    if (in != stdin) fclose(in);
    return 0;
}

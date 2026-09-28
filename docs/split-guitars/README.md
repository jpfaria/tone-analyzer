# Dividir a guitarra separada (demucs) em partes e rotular base/solo

Status: ideia, medida em 2026-09-28, não implementada.

## Problema
`separate` (demucs `--two-stems guitar`) entrega UMA guitarra. Os pares `lead`/`rhythm`
da biblioteca vieram de stems reais (`kind: stem`), nunca do separador.

## Medição (reference.wav do demucs, 2026-09-28)
| música | corr L×R (amostra) | mesma harmonia L×R (croma, mediana / quadros >0.8) | ativo L/R | notas fortes/quadro L/R |
|---|---|---|---|---|
| Creed — My Sacrifice | −0.11 | 0.97 / 100% | 98% / 99% | 2.3 / 2.5 |
| Green Day — Welcome to Paradise | −0.03 | 0.96 / 99% | 98% / 98% | 2.7 / 4.1 |
| John Mayer — Gravity | 0.97 | — | — | — |

- Correlação L×R baixa → duas tomadas diferentes, uma por lado → dá para separar L e R.
- Correlação alta (Gravity) → guitarra no centro, divisão por pan não serve.
- Creed e Green Day: os dois lados são **base dobrada** (mesma harmonia o tempo todo).

## Regra proposta
1. Split por pan só se corr(L,R) < ~0.5; senão, uma parte só.
2. Rótulo por parte:
   - **base**: ativa quase o tempo todo, polifônica (≥2 notas fortes), mesma harmonia do outro lado.
   - **solo**: ativa em trechos, monofônica, harmonia divergente da base.
   - dois lados com mesma harmonia → `rhythm-L` / `rhythm-R` (base dobrada).
3. Solo no centro: testar `mid − (L+R base)` como candidato a solo (não medido).

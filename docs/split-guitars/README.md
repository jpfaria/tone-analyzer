# Dividir a guitarra separada (demucs) em partes e rotular base/solo

Status: implementado em `tone_analyzer/split.py` (`tone-analyzer split`, e o `separate` já roda sozinho), 2026-09-28.

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

## Resultado nas guitarras separadas da biblioteca (2026-09-28)
| música | veredito | partes |
|---|---|---|
| Creed — My Sacrifice | dividida (−0.11) | rhythm-L, rhythm-R |
| Green Day — Welcome to Paradise | dividida (−0.03) | rhythm-L, rhythm-R |
| Green Day — American Idiot | dividida (0.18) | rhythm-L, rhythm-R |
| Green Day — Boulevard | dividida (0.06) | rhythm-L, rhythm-R |
| Pearl Jam — Alive | dividida (0.40) | rhythm-L, rhythm-R |
| Pearl Jam — Even Flow | dividida (0.04) | rhythm-L, rhythm-R |
| Green Day — Good Riddance | centro (0.95) | rhythm |
| John Mayer — Gravity | centro (0.97) | lead |
| Samuel Lima — Quem é Esse | centro (0.72) | undetermined |

## Limites (quando NÃO dá — a ferramenta diz)
- Guitarra no centro ou mono → `split: false` + motivo; uma parte só.
- Parte que não é claramente base nem solo → `undetermined`, nunca chute.
- O rótulo é da música inteira. Solo que entra por cima da base no mesmo lado
  some no rótulo: Even Flow tem o solo no lado L (65 s) sobre a base — no trecho do
  solo o L cai de 4.4 para 3.2 notas simultâneas, mas continua `rhythm-L`.
  Rotular por trecho seria o próximo passo; o sinal medido é fraco.
- O "solo" e a "base" da Even Flow na biblioteca são recortes no tempo da mesma
  separação demucs (correlação 1.00), não stems independentes.

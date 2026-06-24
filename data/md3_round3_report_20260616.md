# World Cup 2026 — Simulating the Next Games (Round 3)

## Headline

With 48 of 72 group games played, this is a **pure-model** read of the final round of group matches — 100,000 Monte-Carlo simulations driven by the engine's Elo→Poisson/Dixon-Coles grids, **no Polymarket or any market odds blended in**. The win/draw/loss probabilities and EV-optimal Kicktipp tips (4/3/2 scoring) below come straight from `md3_full_calc.json`; the advancement reads (P(win)/P(top-2)/P(3rd→advance)/P(advance)) come from `md3_advance_sim.txt`, which uses the full cross-group best-8-thirds race. **The simulator was adversarially verified and independently cross-checked clean:** four review lenses (ranking key, best-3rd selection, accumulation, invariants) found no number-changing bug, and independent Poisson-grid enumerations for Groups A, B, G, H, and I reproduced the sim's within-group win%/top-2% to within ~0.5pp (Monte-Carlo noise). Treat every number as model output, not destiny.

---

## Group A
- **Mexico vs Czechia** — P(W/D/L) 46.8 / 36.4 / 16.8 · EV tip **1:0** (EV 1.44)
- **South Africa vs South Korea** — P(W/D/L) 10.3 / 29.8 / 60.0 · EV tip **0:1** (EV 1.74)
- Table: Mexico 6 (+3), South Korea 3 (0), Czechia 1 (−1), South Africa 1 (−2).
- **Mexico is mathematically clinched** (ADV 100.0%, top-2 100.0%) and a 94.6% favorite to win the group. South Korea is the clear runner-up (top-2 85.4%, ADV 96.2%). Czechia (ADV 20.1%) and South Africa (ADV 10.2%) are alive only via a best-3rd lifeline. **Key:** South Korea just needs to avoid a heavy loss to South Africa to lock 2nd.

## Group B
- **Canada vs Switzerland** — P(W/D/L) 26.6 / 37.3 / 36.1 · EV tip **0:0** (EV 1.34)
- **Bosnia vs Qatar** — P(W/D/L) 58.1 / 31.6 / 10.3 · EV tip **1:0** (EV 1.72)
- Table: Canada 4 (+6), Switzerland 4 (+3), Bosnia 1 (−3), Qatar 1 (−6).
- **Both Canada and Switzerland are effectively through** (ADV 100.0% each); their head-to-head decides only seeding (Canada win 63.8%, Switzerland 36.2%). Bosnia (ADV 58.0%, almost entirely via 3rd→adv 57.6%) is the live third-place contender; Qatar (ADV 10.3%) needs to beat Bosnia to leapfrog. **Key:** Bosnia just needs a win over Qatar to put a strong 3rd-place card on the table.

## Group C
- **Brazil vs Scotland** — P(W/D/L) 54.8 / 32.2 / 13.0 · EV tip **1:0** (EV 1.62)
- **Morocco vs Haiti** — P(W/D/L) 70.0 / 23.9 / 6.1 · EV tip **1:0** (EV 1.94)
- Table: Brazil 4 (+3), Morocco 4 (+1), Scotland 3 (0), Haiti 0 (−4).
- Brazil (ADV 100.0%, win 60.2%) and Morocco (ADV 100.0%, win 35.8%) are both essentially through. Scotland is the live one: top-2 only 13.5% but **ADV 85.7%** on the strength of a 72.2% best-3rd route. Haiti is all but eliminated (ADV 0.3%). **Key:** Scotland advances as a best-3rd in most worlds even with a loss to Brazil, but a result there would secure 2nd.

## Group D
- **USA vs Turkey** — P(W/D/L) 20.3 / 34.8 / 44.9 · EV tip **0:1** (EV 1.36)
- **Paraguay vs Australia** — P(W/D/L) 41.6 / 38.3 / 20.2 · EV tip **0:0** (EV 1.40)
- Table: USA 6 (+5), Australia 3 (0), Paraguay 3 (−2), Turkey 0 (−3).
- **USA is clinched** (ADV 100.0%, win 99.8%). Australia (top-2 58.1%, ADV 86.1%) and Paraguay (top-2 41.9%, ADV 86.5%) fight head-to-head for 2nd, with the loser leaning on the best-3rd route. Turkey (ADV 13.4%) needs help. **Key:** Paraguay vs Australia is a direct knockout for the runner-up spot; even the loser usually survives as a 3rd.

## Group E
- **Germany vs Ecuador** — P(W/D/L) 37.3 / 36.3 / 26.4 · EV tip **0:0** (EV 1.30)
- **Curaçao vs Ivory Coast** — P(W/D/L) 3.5 / 16.4 / 80.2 · EV tip **0:1** (EV 2.06)
- Table: Germany 6 (+7), Ivory Coast 3 (0), Ecuador 1 (−1), Curaçao 1 (−6).
- **Germany is clinched** (ADV 100.0%, win 99.7%). Ivory Coast is a heavy favorite for 2nd (top-2 95.0%, ADV 98.6%). Ecuador (ADV 27.0%) and Curaçao (ADV 3.4%) are best-3rd long shots. **Key:** Ivory Coast just needs to beat winless Curaçao to confirm 2nd.

## Group F
- **Netherlands vs Tunisia** — P(W/D/L) 65.7 / 27.3 / 7.0 · EV tip **1:0** (EV 1.88)
- **Japan vs Sweden** — P(W/D/L) 43.1 / 35.4 / 21.5 · EV tip **1:0** (EV 1.32)
- Table: Netherlands 4 (+4), Japan 4 (+4), Sweden 3 (0), Tunisia 0 (−8).
- Netherlands (ADV 100.0%, win 66.0%) and Japan (ADV 100.0%, win 26.7%) are both through. Sweden is the strong 3rd: top-2 21.4% but **ADV 95.0%** via a 73.6% best-3rd route. Tunisia is eliminated (ADV 0.0%). **Key:** Sweden needs at least a point against Japan — or simply for its 3-point card to hold up — to advance.

## Group G
- **Belgium vs New Zealand** — P(W/D/L) 78.3 / 17.1 / 4.6 · EV tip **1:0** (EV 2.01)
- **Egypt vs Iran** — P(W/D/L) 30.1 / 44.1 / 25.8 · EV tip **0:0** (EV 1.65)
- Table: Egypt 4 (+2), Iran 2 (0), Belgium 2 (0), New Zealand 1 (−2).
- Egypt leads and is essentially safe (ADV 100.0%, win 61.0%) — its 3rd-place fallback still carries 4 pts. **Belgium is the headline jeopardy case:** sitting 3rd on 2 pts, top-2 85.1% but **ADV only 95.1%** (a 4.9% out chance), high for a side of its caliber. Iran (ADV 72.0%) is genuinely live: top-2 31.7% plus a 40.2% best-3rd route. New Zealand (ADV 4.6%) is nearly out. **Key:** Belgium is heavily favored to beat New Zealand, and a win almost certainly sends it through — but a slip-up plus an Egypt–Iran result going the wrong way is its real elimination path.

## Group H
- **Spain vs Uruguay** — P(W/D/L) 55.2 / 33.7 / 11.1 · EV tip **1:0** (EV 1.66)
- **Cape Verde vs Saudi Arabia** — P(W/D/L) 34.5 / 40.5 / 25.1 · EV tip **0:0** (EV 1.48)
- Table: Spain 4 (+4), Uruguay 2 (0), Cape Verde 2 (0), Saudi Arabia 1 (−4).
- Spain is safe (ADV 100.0%, win 88.8%) but **not top-2 clinched** (96.2%) — it can theoretically fall to a (still-qualifying) 3rd. The 2nd spot is a genuine scramble: Cape Verde (top-2 58.2%, ADV 75.0%), Uruguay (top-2 23.1%, ADV 51.1%), Saudi Arabia (top-2 22.4%, ADV 25.2%). **Key:** Cape Verde controls its own fate against Saudi Arabia; Uruguay likely needs a point off Spain.

## Group I
- **France vs Norway** — P(W/D/L) 59.1 / 25.9 / 15.0 · EV tip **1:0** (EV 1.61)
- **Senegal vs Iraq** — P(W/D/L) 73.5 / 21.5 / 5.0 · EV tip **1:0** (EV 1.99)
- Table: France 6 (+5), Norway 6 (+4), Senegal 0 (−3), Iraq 0 (−6).
- **France and Norway are both mathematically clinched** for top-2 (ADV 100.0% each); they play only for the group win (France 85.0%, Norway 15.0%). Senegal and Iraq are mathematically out of the top 2 (top-2 0.0%). Senegal keeps a real best-3rd path (ADV 63.2%); Iraq is all but gone (ADV 2.3%). **Key:** Senegal needs to beat Iraq — and beat it well — to build a qualifying 3rd-place card.

## Group J
- **Argentina vs Jordan** — P(W/D/L) 88.7 / 9.8 / 1.5 · EV tip **2:0** (EV 2.22)
- **Algeria vs Austria** — P(W/D/L) 21.7 / 37.5 / 40.8 · EV tip **0:0** (EV 1.36)
- Table: Argentina 6 (+5), Austria 3 (0), Algeria 3 (−2), Jordan 0 (−3).
- **Argentina is clinched** (ADV 100.0%, win 100.0%). Austria (top-2 78.3%, ADV 96.3%) is favored for 2nd; Algeria (top-2 21.7%, ADV 80.9%) leans on a 59.3% best-3rd route. Jordan is out (ADV 0.5%). **Key:** Austria needs to avoid losing to Algeria; a draw secures 2nd.

## Group K
- **Portugal vs Colombia** — P(W/D/L) 40.9 / 36.6 / 22.5 · EV tip **0:0** (EV 1.32)
- **DR Congo vs Uzbekistan** — P(W/D/L) 34.3 / 39.9 / 25.9 · EV tip **0:0** (EV 1.46)
- Table: Colombia 6 (+3), Portugal 4 (+5), DR Congo 1 (−1), Uzbekistan 0 (−7).
- **Both Colombia and Portugal are through** (ADV 100.0% each); their head-to-head decides the group (Colombia win 58.9%, Portugal 41.1%). DR Congo (ADV 37.3%, all best-3rd) is the live outsider; Uzbekistan (ADV 7.5%) is a long shot. **Key:** DR Congo needs to beat Uzbekistan to build a viable 3rd-place card.

## Group L
- **England vs Panama** — P(W/D/L) 79.2 / 17.4 / 3.4 · EV tip **1:0** (EV 2.07)
- **Croatia vs Ghana** — P(W/D/L) 65.7 / 26.9 / 7.5 · EV tip **1:0** (EV 1.86)
- Table: England 4 (+2), Ghana 4 (+1), Croatia 3 (−1), Panama 0 (−2).
- England is safe (ADV 100.0%, win 83.9%). Remarkably, **all three of England, Ghana, and Croatia advance in essentially every sim** (Ghana ADV 100.0%, Croatia ADV 98.0%) — Ghana via top-2 34.3% + best-3rd 65.7%, Croatia via top-2 65.7% + best-3rd 32.3%. Panama is out (ADV 0.2%). **Key:** Croatia is favored to beat Ghana and take 2nd; the loser of that match still advances as a strong 3rd in nearly all worlds.

---

## Biggest jeopardy & the best-3rd cut line

**Favorites at real risk.** The standout is **Belgium** (Group G): a pre-tournament heavyweight sitting 3rd on 2 points, with model **ADV 95.1% — i.e. a ~1-in-20 chance of going home** despite being a strong favorite (78.3%) to beat New Zealand. Its fate is partly hostage to the Egypt–Iran result. Lesser scares: **Iran** at 72.0% (live but not safe) and **Uruguay** at 51.1% (a literal coin-flip to survive Group H). Among genuine contenders, **Cape Verde** (75.0%) and **Senegal** (63.2%, entirely via the 3rd-place route) also carry meaningful exit risk.

**Best-3rd cut line (current standings snapshot).** With two of the eight best-3rd berths effectively spoken for by safe groups, the live race among third-placed teams currently sorts on Pts·GD·GF as: **in** — Sweden (F, 3/+0/6), Scotland (C, 3/+0/1), Croatia (L, 3/−1/3), Algeria (J, 3/−2/2), Paraguay (D, 3/−2/2), Cape Verde (H, 2/+0/2), Belgium (G, 2/+0/1), Czechia (A, 1/−1/2); **out, first to miss** — DR Congo (K, 1/−1/1), then Ecuador (E, 1/−1/0), Bosnia (B, 1/−3/2), Senegal (I, 0/−3/3). The cut presently bites right at the **1-point line**: Czechia holds the 8th-and-last spot on goals scored over DR Congo and Ecuador, so a single goal in Round 3 can flip the final qualifier. Note this ordering is a snapshot of the published standings; the simulator's ADV figures already integrate every Round-3 result distribution and the full cross-group race.

*All probabilities are pure-model (no market). Source files: `data/md3_advance_sim.txt`, `data/md3_full_calc.json`, `data/group_standings_20260616.txt`.*

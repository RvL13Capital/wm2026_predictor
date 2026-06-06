## 2026-06-03T17:09:08Z
Analyze the current implementation in `predictor.py` at `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/predictor.py`. Propose a detailed design and mathematical implementation strategy for:
1. Bivariate Poisson with Dixon-Coles correlation adjustments to properly model draws. Describe the exact correction formula for low scores (0-0, 1-0, 0-1, 1-1) with correlation parameter rho.
2. Negative Binomial distribution to handle overdispersion (high-scoring outliers) where variance exceeds the mean. Explain the parameters (e.g., dispersion parameter alpha or r, p) and how probabilities for goal counts are computed.
Define clear function signatures and data structures. Write your report to `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/explorer_m2_1/analysis.md` and report back when finished.

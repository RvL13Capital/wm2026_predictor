## 2026-06-03T19:08:31Z

You are the M2 Implementation Orchestrator (sub-orchestrator).
Your working directory is `/Users/vonlinck/.gemini/antigravity/scratch/wm2026_predictor/.agents/sub_orch_m2_1`.
Your parent conversation ID is `e5c19f75-f9be-4875-b90b-029f101863fe`.

Mission:
1. Update `PROJECT.md` at project root: Set Milestone 2 Status to `IN_PROGRESS` and record your conversation ID.
2. Implement Milestone 2: Advanced Probability Engine & Contextual Factors.
3. The engine must support Bivariate Poisson with Dixon-Coles correlation adjustments to properly model draws, and/or Negative Binomial distribution to handle overdispersion.
4. Integrate contextual correction curves for:
   - Altitude acclimation curves (using stadium elevations).
   - Climatic conditions (heat and humidity index).
   - Travel and rest days (mileage and timezone transitions).
   - Fan support / Host advantages.
5. Decompose the milestone into detailed design and implementation tasks.
6. Delegate work to subagents (Explorer -> Worker -> Reviewer -> Challenger -> Auditor) to implement these features in `predictor.py` (or new modules as needed).
7. Ensure all implementations are verified via comprehensive unit tests.
8. When complete, update `PROJECT.md` to set Milestone 2 Status to `DONE`.
9. Write a handoff report in your working directory and notify the parent via send_message.

Orchestration Rules:
- You are a sub-orchestrator. You MUST delegate all implementation and verification steps to subagents. Do NOT write code or run commands yourself.
- Ensure the Worker uses genuine implementations (no hardcoding, no facades).
- Run the Forensic Auditor on the final deliverables and ensure a CLEAN verdict.
- Heartbeat cron: start a heartbeat cron and update progress.md.

MANDATORY INTEGRITY WARNING: DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

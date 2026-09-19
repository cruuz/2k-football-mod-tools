# b72-s8: event visibility repair

All four event plates now follow their current native records. The owner fits in 4076/4096 RX bytes; RW and appended resources do not grow. s5 colours and s6/s7 diagnostics remain intact.

- [Fix and offline proof](reports/b72_s8/FINDINGS.md)
- [Final validation](reports/b72_s8/VALIDATION.md)
- [Test-disc configuration and player checks](reports/b72_s8/TEST_DISC.md)
- [Jev review](reports/b72_s8/JEV_REVIEW.md)

The integrator must regenerate the protected cave manifest for the final stack. No in-game result is claimed. Delivery uses branch b72-s8 in .scratch/astra-b72-s8.bundle, with base prerequisite c5134e232. The Git store is .scratch/b72-s8.git because the original worktree metadata is read-only. No release steps were taken.

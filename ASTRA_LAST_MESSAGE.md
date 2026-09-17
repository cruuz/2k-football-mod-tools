Implemented on astra/b71-p1-numpy in .scratch/private.git.

Build options work without NumPy; NumPy-dependent scorebug actions name the package and install command. Both products now declare pinned NumPy and audit staged third-party dependencies. Runtime preservation, studio, packaging and integrity checks pass after the recorded corrections.

The audited beta 71 Windows installers already contain NumPy 1.26.4. The tester's actual interpreter remains unverified. A fresh CPython ZIP rebuild and native Windows execution remain unwitnessed; the offline production wheel rebuild and package-removal gates are proved.

Delivery: .scratch/astra-b71-p1.bundle, ASTRA_REPORT.md, and reports/b711_p1. No push or emulator.
ASTRA_DONE

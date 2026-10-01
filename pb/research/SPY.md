# DESIGN: bounded situational Spy authoring

INFERRED: Steve Spagnuolo uses a dedicated quarterback spy situationally against mobile quarterbacks. Eric Edholm's [NFL report on the January 28, 2024 AFC Championship](https://amp.nfl.com/news/chiefs-defense-was-dirty-tough-in-locking-down-ravens-for-afc-title-game-win) identifies Leo Chenal as the early spy on Lamar Jackson. [Spagnuolo's October 30, 2025 remarks before facing Josh Allen](https://www.si.com/nfl/chiefs/onsi/kansas-city-steve-spagnuolo-nohl-williams-josh-allen/) describe mixing a spy with other rush plans according to situation. These establish use, not a measured season frequency. Sources checked September 25, 2026.

DESIGN: KC gets one spot-zone call with a native MLB Spy assignment through `DefenseDesign.set_assignment(..., 'spy')`. The existing authoring writer emits the versioned intent, and the existing QB Spy owner supplies quarterback tracking. The call keeps its coverage family and four-rusher count. The four-yard centered shallow zone is its fallback when the runtime is absent. No new opcode or runtime behavior is invented.

DESIGN: One menu call is an availability choice, not an estimate of 2025 frequency or a quarterback-aware CPU selection rule. This implementation uses the native MLB slot, not a claim that a particular 2026 roster player occupies Chenal's earlier role. All other team defense receipts and all complete-offense receipts explicitly contain empty Spy records. Absence of a sourced call in this pack is not evidence that another DC never uses spies.

DESIGN: Runtime table capacity remains 31 assignments league-wide. This pack uses one. Live pursuit, selection against mobile quarterbacks and pressure behavior still need main's lab.

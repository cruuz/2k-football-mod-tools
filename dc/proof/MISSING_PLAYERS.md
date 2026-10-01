# PROVED OFFLINE: snapshot matching and missing-player ledger

PROVED OFFLINE: latest snapshot is selected independently for each team. All 32 supplied latest values are 2026-09-28T06:01:42Z. Source: nflverse contributors, depth_charts_2026.csv, CC-BY-4.0. The 2025 file is not used to fill 2026 assignments. [Full input hashes, candidates and match methods](import.json).

| Team | Role | Missing rank | Missing player | Selected role depth | Evidence |
|---|---|---|---|---|---|
| SF | KR | 3 | Isaac Guerendo | Deebo Samuel, Jacob Cowing | PROVED OFFLINE |
| SF | PR | 3 | Ricky Pearsall | Jacob Cowing | PROVED OFFLINE |
| BUF | KR | 1 | Greg Dortch | Ray Davis, Ty Johnson | PROVED OFFLINE |
| BUF | PR | 1 | Greg Dortch | Dee Alford | PROVED OFFLINE |
| DEN | KR | 2 | Kolbe Katsis | Marvin Mims, Tyler Badie | PROVED OFFLINE |
| DEN | PR | 2 | Kolbe Katsis | Marvin Mims | PROVED OFFLINE |
| DEN | LS | 1 | Mitchell Fraboni | Alex Forsyth | DESIGN |
| CLE | KR | 2 | Dylan Sampson | Malachi Corley, KC Concepcion | DESIGN |
| LAC | KR | 4 | KeAndre Lambert-Smith | Derius Davis, Keaton Mitchell | PROVED OFFLINE |
| LAC | PR | 3 | KeAndre Lambert-Smith | Derius Davis | PROVED OFFLINE |
| DAL | KR | 2 | Malik Davis | KaVontae Turpin, Caleb Downs | DESIGN |
| NYG | KR | 1 | Braxton Berrios | Deonte Banks, Tyrone Tracy | PROVED OFFLINE |
| NYG | PR | 1 | Braxton Berrios | Jevon Holland | PROVED OFFLINE |
| NYG | PR | 3 | Calvin Austin III | Jevon Holland | PROVED OFFLINE |
| NYG | PR | 4 | Gunner Olszewski | Jevon Holland | PROVED OFFLINE |
| NYJ | PK | 1 | Jason Sanders | Blake Grupe | PROVED OFFLINE |
| GB | KR | 3 | Savion Williams | Bo Melton, Skyy Moore | PROVED OFFLINE |
| CAR | KR | 4 | Trevor Etienne | John Metchie, Xavier Legette | PROVED OFFLINE |
| CAR | PR | 5 | Trevor Etienne | John Metchie | PROVED OFFLINE |
| NE | P | 2 | Bryce Baringer | Mitch Wishnowsky | PROVED OFFLINE |
| NE | H | 2 | Bryce Baringer | Mitch Wishnowsky | PROVED OFFLINE |
| BAL | KR | 4 | Adam Randall | Rasheen Ali, LaJohntay Wester | PROVED OFFLINE |
| NO | KR | 3 | Mason Tipton | Barion Brown, Kendre Miller | PROVED OFFLINE |
| NO | KR | 4 | Ty Chandler | Barion Brown, Kendre Miller | PROVED OFFLINE |
| NO | PR | 3 | Mason Tipton | Barion Brown | PROVED OFFLINE |
| NO | LS | 1 | Cal Adomitis | Will Sherman | DESIGN |
| NO | LS | 2 | Zach Wood | Will Sherman | DESIGN |
| PIT | KR | 4 | Donte Kent | Kaden Wetjen, Eli Heidenreich | PROVED OFFLINE |
| PIT | PR | 4 | Donte Kent | Kaden Wetjen | PROVED OFFLINE |
| HOU | PR | 3 | Tank Dell | Jaylin Noel | PROVED OFFLINE |
| MIN | P | 2 | Johnny Hekker | Brett Thorson | PROVED OFFLINE |
| MIN | H | 2 | Johnny Hekker | Brett Thorson | PROVED OFFLINE |

DESIGN: when no remaining KR entry exists, use the first distinct available PR entry. This gives CLE KR2 KC Concepcion and DAL KR2 Caleb Downs; neither is represented as an nflverse KR2 assignment.

DESIGN: exhausted LS lists retain a native local fallback. DEN uses backup center Alex Forsyth because Mitchell Fraboni is missing. NO uses the existing native fallback because both Cal Adomitis and Zach Wood are missing and Erik McCoy is the only center. Adding those missing players requires a separate roster-owner decision.

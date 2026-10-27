# Ordinary sprint parity

Studio's Player Abilities build now uses the same ordinary tap-burst curve for
human players and native CPU sprint requests. The SOFTDRINK presets already
select Player Abilities. No extra recipe switch or roster migration is needed.

At full condition the bonus is 4% at Speed 65, 6% at 75 and 10% at 90 or higher,
with linear interpolation between those points. Burst duration is 0.25 seconds
at 65, growing to 0.50 seconds at 90. Lower ratings keep the native ordinary
burst. Condition still scales the bonus. Genuine repeat commands refresh expiry
without resetting elapsed animation time or removing the native repeat bonus.
The human curve has not changed.

The CPU already issues ordinary sprint commands. Its native decisions about open
running lanes, pursuit and active targets are retained. Full throttle and the
animation state's synthesized held-input command do not create extra tap events.
The change makes an existing CPU request receive the same rating-scaled benefit
as the same human request. It does not force every CPU player to sprint every
frame.

With **star-only charge** selected, a movement superstar must have all of:

- The existing roster-star charge grant, including the configured tier access.
- Raw Speed from 90 through 127.
- Raw Agility from 85 through 127.

The upper bounds reject invalid signed rating bytes. This is a sprint-specific
rating definition, not an overall-rating calculation. Speedster remains the
separate permission for the above-retail Speed extension; adding Speedster alone
does not grant charge. The rule covers CPU and human carriers and defenders,
including direct consumption of a stale meter. Off-week and native permission
checks remain in force. An allowed charged burst retains native 1.5-second
arithmetic. Turning the star-only charge option off retains the existing charge
policy.

Implementation reuses the existing 512-byte sprint child and 1,344-byte abilities
owner. It adds no code/data reservation, hook, mutable timer or runtime dependency.
The historical `apply()` entry points retain the exact older pinned repair
outputs. Studio's build adapter uses `abilities_runtime.apply_shared()`, and
readers validate either complete known profile and its matching hooks.

Native Unicorn replay verifies commands, charge, burst timing and animation-rate
arithmetic. It does not simulate collisions, full play selection, world movement
or rendering. Emulator integration must still check burst animations, matched
human/CPU carries, separation, yards after contact and sustained play stability.

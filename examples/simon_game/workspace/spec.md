# Simon Says Memory Game

A playable "Simon" memory game as a synchronous FSM. On power-on the four LEDs
idle; the first button press seeds a pseudo-random sequence and starts the game.
Each round the design plays back a growing sequence on `led1..led4` (with a tone
on the buzzer and the round number on a 7-segment score display), then waits for
the player to repeat it on `btn1..btn4`. A correct full repeat advances the
round and adds one new step; a wrong press ends the game. The exact same growing
sequence is replayed each round with one new symbol appended — the classic Simon
behaviour.

## Attribution
The game core (`simon.v`: the `simon` FSM plus its `score` 7-segment and `play`
tone back-ends) is adapted from **Uri Shaked's Tiny Tapeout TT06 project
`tt06-simon-game`** (https://github.com/urish/tt06-simon-game, commit
`37f3538ba18fb3eeea73ad37d0f36e631189ae75`).

**Licensing — please read (dual):** the upstream source file `src/simon.v`
carries a per-file **MIT** SPDX header (`© 2023 Uri Shaked`); the repository's
`LICENSE` file is the stock Tiny Tapeout **Apache-2.0** template. Both are
permissive OSI licenses. This bundle honours both: the repo's Apache-2.0
`LICENSE` is copied to the bundle root, the MIT copyright notice and full MIT
permission text are preserved inside `simon.v`, and the origin repo+commit are
recorded here and in `template.json`.

**Adaptation.** The upstream chip wraps the game in the fixed Tiny Tapeout pin
interface (`ui_in`/`uo_out`/`uio_*`/`ena`), routing the 7-segment digits out over
the bidirectional `uio` bus. This bundle:
- drops the pin wrapper and exposes real named ports on a clean top
  (`simon_game.v`);
- drops the upstream `wokwi` module (a Wokwi-simulator top, not part of the
  chip);
- adds three **observability taps** to the `simon` core — `game_over`, `level`,
  `dbg_state` — which are pure reads of existing state registers (no behaviour
  change) so the testbench has a deterministic oracle;
- makes the game's "millisecond" tick a parameter (`TICKS_PER_MILLI`) so
  simulation runs fast while synthesis uses the real value.
The `score` (7-segment) and `play` (tone) back-ends are kept verbatim, so the
synthesized design is the full playable game, not a stripped datapath.
The self-checking testbench (`simon_game_tb.v`) is **original** to this bundle.

## Interface (`simon_game`)
| Signal          | Dir | Width | Description                                        |
|-----------------|-----|-------|----------------------------------------------------|
| clk             | in  | 1     | Clock                                              |
| rst_n           | in  | 1     | Active-low synchronous reset                       |
| btn             | in  | 4     | Buttons btn1..btn4 (one-hot press)                 |
| led             | out | 4     | LEDs led1..led4 (sequence playback / input echo)   |
| sound           | out | 1     | Buzzer square wave                                 |
| segments        | out | 7     | 7-segment score digit (active-high)                |
| segment_digits  | out | 2     | Which score digit is currently driven (mux)        |
| game_over       | out | 1     | High when the player has lost                      |
| level           | out | 5     | Rounds survived (score)                            |
| dbg_state       | out | 3     | Raw FSM state (observability tap)                  |

## Parameters
| Name            | Default | Meaning                                          |
|-----------------|---------|--------------------------------------------------|
| TICKS_PER_MILLI | 50      | Clock ticks per game-millisecond (50 kHz clock). The testbench overrides it to 2 for fast simulation. |

## Verification
The original self-checking testbench plays a full game deterministically through
the real I/O contract. It does **not** hard-code the pseudo-random sequence:
instead it *observes* the LED playback to learn each round's sequence, then
replays it on the buttons — so the run is fully deterministic (fixed clock +
fixed press timing) while still checking real game behaviour. It asserts:
1. reset reaches power-on and a button press starts round 1;
2. round 1's single symbol, replayed correctly, advances the level (1 → 2) with
   no game-over;
3. round 2 replays round 1's first symbol plus one new one (the growing-sequence
   invariant);
4. a deliberate wrong button press in round 2 drives the design to game-over.
On success it prints `TEST PASSED`. Then the design is synthesized to GDSII on
sky130hd (synthesis uses the real 50 kHz-clock `TICKS_PER_MILLI`).

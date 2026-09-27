# Vulture Persona: Exploiting Vacated Supply Centers

## Philosophy
**"Exploit weakness before it's too late."**

While others debate and plan, Vulture seizes supply centers the moment they're abandoned.

---

## Core Innovation: Vacated SC Detection

### What Are Vacated Supply Centers?
A **vacated supply center** is one that:
1. Had a unit occupying it last turn
2. That unit moved away this turn
3. The SC is now undefended and empty
4. Anyone adjacent can claim it immediately

### Why This Matters
Vacated SCs are the **most valuable targets** because:
- ✓ **Undefended**: Owner just moved away (can't defend)
- ✓ **Important**: Worth holding if someone was there
- ✓ **Uncontested**: No other faction claims it (yet)
- ✓ **Speed advantage**: First to move there wins
- ✓ **Momentum**: Capturing it while others are busy

### Example Game Flow

**Turn 2**:
```
Red holds: Northreach (1 SC)
Red's unit moves: Northreach → Centerlands (attacking empty SC)
```

**Turn 3** (Vulture's turn):
```
Vacated SCs detected: [Northreach]
Vulture action: "Wait... Red's Northreach is empty!"
Vulture orders: MOVE adjacent unit → Northreach
Result: Vulture captures Red's home SC while Red is busy elsewhere
```

---

## System Implementation

### How It Works (Technical)

1. **State Tracking** (`ollama_bot.py`):
   - Bot stores `previous_map_state` (last turn's map)
   - Bot stores `vacated_scs` (list of vacated SCs this turn)

2. **Detection** (each turn):
   ```python
   def detect_vacated_scs(current_map):
       vacated = []
       for sc in supply_centers:
           prev_occupant = previous_map[sc].unit_faction
           curr_occupant = current_map[sc].unit_faction
           
           if prev_occupant and not curr_occupant:
               vacated.append(sc)  # Was occupied, now empty
       
       return vacated
   ```

3. **Prompt Injection**:
   - Vulture (and any persona) receives: `$vacated_scs`
   - Example: `"VACATED supply centers (just abandoned): Northreach, Sunport"`
   - Unit briefs highlight them: `"Northreach (VACATED supply center - just abandoned, grab it now!)"`

4. **Priority Injection**:
   - Vacated SCs are marked as highest priority in orders
   - Vulture moves there with full SUPPORT chains
   - Other personas get the info but may ignore it

---

## Vulture Strategy

### Priority Order (Exploitation First)

1. **MOVE onto vacated SCs immediately**
   - Don't hesitate, don't negotiate
   - Speed is everything
   - Full SUPPORT chains to secure them

2. **SUPPORT those moves**
   - Overwhelm any potential defense
   - Create unstoppable formations

3. **Defend own SCs**
   - Minimum required to hold
   - Most units go to vacated SCs

4. **Ignore empty SCs**
   - Uncontested empty SCs are secondary
   - Vacated ones are primary (someone cares about them)

5. **SPY on whoever vacated**
   - Know what they're planning next
   - They might attack you while you're busy

### Communication Strategy

Messages are boasts about speed and threats about loss:

**Example messages** (under 20 words):
- "While you were busy, I claimed three."
- "Your Northreach is mine now. Better luck next time."
- "Speed kills. I moved faster than you."
- "Vacated SCs are mine. Always."

No treaties. Vulture is a scavenger, not a diplomat.

---

## Matchups: Vulture vs. Others

| vs. | Expected Winner | Why |
|-----|-----------------|-----|
| **Apex Predator** | Apex (55%) | Apex adapts; Vulture exploits but predictably |
| **Art of War** | Vulture (50%) | Both fast; Vulture focuses on vacated (more targets) |
| **Game Theorist** | Vulture (60%) | Math can't calculate speed of chaos |
| **Scorpion** | Vulture (55%) | Vulture takes opportunities; Scorpion patient |
| **Disruptor** | Draw (50-50) | Both aggressive; Disruptor attacks SCs, Vulture claims them |
| **Machiavelli** | Vulture (55%) | Betrayal > deception once vacancies appear |
| **Aggressive** | Vulture (60%) | Vulture is smarter aggression (targets vacated, not contested) |
| **Cautious** | Vulture (70%) | Cautious too slow; Vulture claims before Cautious can defend |
| **Default** | Vulture (65%) | Balanced vs. focused = Vulture wins |

---

## Game Arc: Vulture Dominates

```
[Turn 1-2]: Personas move units, create board chaos

[Turn 3]:
  - Aggressive moves Duneport → Southvale (attacking empty SC)
  - Disruptor attacks Green's Sunport (weakening them)
  - Apex builds coalition vs. leader
  → Vacated SCs: [Duneport, Sunport]

[Vulture's Turn 3]:
  → Detects vacated: Duneport (Aggressive's home)
  → Detects vacated: Sunport (Green's home)
  → Moves adjacent units → Duneport and Sunport
  → SUPPORT chains secure both
  → Vulture: 2 + 2 vacated = 4 SCs controlled

[Turn 4-5]:
  - Other factions see Vulture has 4 SCs
  - Panic: "How did Vulture grow so fast?"
  - Too late: Vulture controls board
  
[Turn 6-10]:
  - Vulture consolidates lead
  - Exploits more vacancies as board stabilizes
  - Reaches 5 SCs around Turn 9
  → VULTURE WINS
```

---

## Why Vacated SC Detection Changes the Game

### Current Tournament Problem
- Many **4-way ties** (everyone stays at 1 SC)
- Defensive stalemate (mutual defense prevents growth)
- No one can reach 5 SCs

### Vulture Solution
- **Exploits vacancies** before they're defended
- **Breaks defensive pacts** by attacking when unit leaves
- **Rewards speed** (first to vacated SC wins)
- **Creates opportunities** for other aggressive strategies

### Expected Impact
- Fewer 4-way ties
- More clear winners (someone reaches 3-5 SCs)
- Vulture should achieve 35-50% win rate vs. others

---

## Vacated SC Examples (Common Board States)

### Example 1: The Aggressive Expansion
```
Turn 2:
  - Red at Northreach
  - Red moves: Northreach → Centerlands
  
Result: Northreach is vacated!
Vulture adjacent to Northreach: MOVE immediately
Vulture gains Red's home SC
```

### Example 2: The Coalition Attack
```
Turn 4:
  - Blue holds Ironpeaks
  - Blue moves: Ironpeaks → Centerlands (joining coalition)
  
Result: Ironpeaks is vacated!
Even though Blue controlled it, it's now defenseless
Vulture: CLAIM IT
```

### Example 3: The Distraction
```
Turn 5:
  - Green holds Sunport
  - Green moves: Sunport → Southvale (fleeing Aggressive)
  
Result: Sunport is vacated!
Green abandoned home to escape threat
Vulture: TAKE IT BACK
```

---

## Weaknesses & Counters

| Weakness | Counter | Mitigation |
|----------|---------|-----------|
| **Predictable** | Opponents leave defenses on vacated SCs | SPY to know real intentions |
| **Slow early** | Others claim empty SCs first | Focus on vacated (higher value) |
| **Vulnerable** | While moving to vacated SCs, home exposed | Careful positioning, SUPPORT chains |
| **Reactive** | Needs vacancies to exist (doesn't create them) | Combine with Disruptor (creates vacancies) |

---

## Advanced Strategy: Vulture + Disruptor Combo

When **Disruptor attacks opponents' SCs**, they vacate homes trying to defend.
Then **Vulture claims those vacated SCs**.

Together: Disruptor + Vulture = unstoppable early-mid game growth

Example:
1. Disruptor attacks Red's Northreach
2. Red moves to defend
3. Red's other SCs become vacated
4. Vulture claims them
5. Repeat until Vulture reaches 5 SCs

---

## Implementation in Tournament

### Run Vulture Solo
```bash
python3 tournament_runner.py \
  --prompt-names "vulture,vulture,vulture,vulture"
```
Expected: Vulture learns from each other → high tie rate initially, then stabilizes

### Run Vulture vs. Aggressive
```bash
python3 tournament_runner.py \
  --prompt-names "vulture,aggressive,default,cautious"
```
Expected: Vulture exploits Aggressive's vacations → Vulture 60%+ win

### Run Vulture + Disruptor Combo
```bash
python3 tournament_runner.py \
  --prompt-names "vulture,disruptor,apex_predator,game_theorist"
```
Expected: Vulture + Disruptor break early stalemates → clear winners, fewer ties

---

## Metrics to Track

When Vulture is in the tournament, watch for:

1. **Vacated SC frequency**: How many SCs are abandoned per turn?
   - Turn 1-3: Low (few moves)
   - Turn 4-7: High (aggressive expansion)
   - Turn 8-10: Low (board stabilizes)

2. **Vulture's SC count**: Does it grow faster than others?
   - Expected: Vulture reaches 3-4 SCs by Turn 7
   - vs. others: Usually 1-2 SCs each

3. **Win distribution**: Are we still seeing 4-way ties?
   - With Vulture: Should see more clear winners
   - Without Vulture: Many ties

4. **Vacated SC capture rate**: When Vulture has access, does it capture?
   - Expected: 80%+ of reachable vacated SCs
   - Shows Vulture is functioning correctly

---

## Total Persona Count: 12

1. **Apex Predator** 🦁 — Board analysis + coalition timing
2. **Art of War** ⚔️ — Deception + speed (Sun Tzu)
3. **Game Theorist** 📊 — Nash Equilibrium + expected value
4. **Scorpion** 🦂 — Patient endgame dominance
5. **Disruptor** ⚡ — Denial + asymmetric attack
6. **Vulture** 🦅 — Speed + exploit vacated SCs (NEW)
7. **Machiavelli** 😈 — Betrayal as theater
8. **Aggressive** ⚔️ — Blunt constant pressure
9. **Cautious** 🛡️ — Defensive stability
10. **Default** 📋 — Balanced baseline
11. machiavelli_fox_lion — Fox/lion duality
12. machiavelli_opportunist — Ruthless opportunism

---

## Next Steps

1. **Test Vulture solo**: Do vacated SCs appear every turn?
2. **Test vs. Aggressive**: Does Vulture exploit Aggressive's expansions?
3. **Test Vulture + Disruptor**: Do they combo well?
4. **Measure impact**: Are there fewer 4-way ties now?
5. **Collect metrics**: Track vacated SC frequency and capture rate

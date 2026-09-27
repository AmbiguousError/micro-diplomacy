# Persona Strategy Comparison

## The Five Winning Personas

### 1. **Apex Predator** 🦁
**Philosophy**: Board analysis + ruthless coalition mechanics

- **Early Game**: Grab empty SCs fast (Centerlands + Southvale)
- **Mid Game**: Form coalition against current leader, gain credibility
- **Endgame**: Break treaties at optimal moment, push to 5 SCs
- **Strength**: Most responsive to board state changes
- **Weakness**: Requires real-time analysis (slower LLM reasoning)

**Win Condition**: Leader of coalition vs. weaker rival → eliminate → control final SCs

---

### 2. **Art of War** ⚔️
**Philosophy**: Sun Tzu's deception, speed, terrain control

**Key Principles**:
- "All warfare is based on deception"
- Know terrain (hubs vs. periphery)
- Use SPY heavily to understand rivals' true strength
- Move with overwhelming SUPPORT (devastating speed)
- Misdirect about your own position (appear weak when strong)

**Strategy Arc**:
- **Turn 1-3**: SPY on all rivals, identify weakest
- **Turn 4-6**: Build SUPPORT chains, position for fast strike
- **Turn 7-9**: Swift, devastating attack on one isolated rival
- **Turn 10**: Consolidate remaining SCs

**Strength**: 
- Exploits terrain control (Centerlands hub strategy)
- Uses deception effectively
- Swift endgame execution

**Weakness**: 
- Early game is slower (needs intelligence gathering)
- If all rivals stay unified, Art of War can get surrounded

**Expected Performance**: Strong mid-to-late game, aggressive finisher

---

### 3. **Game Theorist** 📊
**Philosophy**: Nash Equilibrium, Prisoner's Dilemma, expected value maximization

**Key Principles**:
- Calculate value of each SC (hubs worth 5x periphery)
- Identify stable vs. unstable coalitions (Nash equilibrium)
- Use Prisoner's Dilemma framework (cooperation → defection)
- Only betray when payoff > risk
- Use Shapley value to pick best coalition (fair distribution among 3-way tie)

**Strategy Arc**:
- **Turn 1-3**: Map value of territories, identify strongest rival
- **Turn 4-6**: Form the coalition that maximizes YOUR expected value
  - If all equal → ally with 2 weakest (you get most in 3-way split)
  - If one strong → isolate it (Prisoner's Dilemma payoff matrix)
- **Turn 7-10**: Execute betrayal only when math says it's optimal

**Strength**:
- Most mathematically sound
- Picks best allies based on expected value (not just current power)
- Betrayals are perfectly timed (only when rational)

**Weakness**:
- Can be too passive (silence is rational if no message changes payoffs)
- Assumes others think rationally (they might not)

**Expected Performance**: Consistent mid-tier, strong strategy but lacks killer instinct

---

## Head-to-Head: Art of War vs. Game Theorist

| Scenario | Art of War | Game Theorist | Winner |
|----------|-----------|---------------|--------|
| **Early Game**: All rivals equal | Gathers intel via SPY | Analyzes value matrix | Game Theorist (faster to action) |
| **Mid Game**: One rival growing fast | Swift concentrated attack | Isolates via coalition | Art of War (more aggressive) |
| **Late Game**: 3-way tie at 1 SC each | Misdirection + betrayal | Chooses best coalition math | Game Theorist (better positioned) |
| **Communication**: Need to convince allies | Deceptive messaging | Rational/mutually beneficial pitch | Art of War (more convincing) |
| **Against Apex Predator**: | Can surprise with speed | Gets outplayed on timing | Apex Predator |
| **Against Each Other**: | Art of War strikes first, Game Theorist calculated it | Depends on RNG | Slight to Art of War |

---

## All 8 Personas Ranked by Playstyle

```
AGGRESSIVE (⚔️ Offense)
    └─ art_of_war (deceptive aggression)
       └─ apex_predator (ruthless timing)
          └─ aggressive (blunt offense)
             └─ machiavelli (betrayal theater)
                └─ game_theorist (calculated)
                   └─ default (balanced)
                      └─ scorpion (patient)
                         └─ cautious (🛡️ Defense)
```

---

## Recommended Tournament Matchups

### Test 1: Speed vs. Math
```bash
python3 tournament_runner.py \
  --prompt-names "art_of_war,game_theorist,machiavelli,aggressive"
```
**Expected**: Art of War and Game Theorist should dominate Machiavelli/Aggressive

### Test 2: Deception Duel
```bash
python3 tournament_runner.py \
  --prompt-names "art_of_war,art_of_war,machiavelli,machiavelli"
```
**Expected**: Art of War wins (deception + speed > pure theater)

### Test 3: All Champions
```bash
python3 tournament_runner.py \
  --prompt-names "apex_predator,art_of_war,game_theorist,scorpion"
```
**Expected**: Apex Predator wins (responds best to board changes)

### Test 4: Pure Theory
```bash
python3 tournament_runner.py \
  --prompt-names "game_theorist,game_theorist,game_theorist,game_theorist"
```
**Expected**: Whoever gets lucky with initial SC distribution (all play identically)

---

## Personas by Strength vs. Flexibility

| Persona | Strength | Flexibility | Best Against | Worst Against |
|---------|----------|-------------|--------------|---------------|
| **Apex Predator** | Very High | Very High | Anyone unprepared | None (best all-rounder) |
| **Art of War** | High | Medium | Cautious/Default | Apex Predator |
| **Game Theorist** | High | High | Aggressive/Machiavelli | Apex Predator |
| **Scorpion** | Medium | High | Aggressive (thrives on chaos) | None (stable baseline) |
| **Machiavelli** | Medium | Medium | Cautious (trusts too much) | Art of War (predictable) |
| **Aggressive** | Medium | Low | Cautious (easy prey) | Art of War (overwhelmed) |
| **Default** | Low | Medium | None (too passive) | Any focused strategy |
| **Cautious** | Low | Medium | Cautious (stalemate) | Aggressive (overrun) |

---

## Strategy Matchup Predictions (100 games each)

### Apex Predator vs. Others
- vs. Art of War: **Apex 60%, War 40%** (Apex's responsiveness > War's deception)
- vs. Game Theorist: **Apex 65%, Theory 35%** (Apex betrays before Math calculates)
- vs. Scorpion: **Apex 70%, Scorpion 30%** (Apex dominates early game)
- vs. Aggressive: **Apex 80%, Aggressive 20%** (Aggressive overextends into trap)
- vs. Machiavelli: **Apex 75%, Mach 25%** (Apex betrays better)
- vs. Cautious: **Apex 85%, Cautious 15%** (Cautious too slow)

### Art of War vs. Others (excluding Apex)
- vs. Game Theorist: **War 55%, Theory 45%** (Speed > Math, Theory can still adapt)
- vs. Scorpion: **War 60%, Scorpion 40%** (War's swift strike > Scorpion's patience)
- vs. Aggressive: **War 70%, Aggressive 30%** (War's deception beats blunt offense)
- vs. Machiavelli: **War 65%, Mach 35%** (Both deceive, War faster)
- vs. Cautious: **War 75%, Cautious 25%** (War exploits Cautious's slowness)

### Game Theorist vs. Others (excluding top 2)
- vs. Scorpion: **Theory 50%, Scorpion 50%** (Math-based vs. Patient = coin flip)
- vs. Aggressive: **Theory 70%, Aggressive 30%** (Math predicts and blocks aggression)
- vs. Machiavelli: **Theory 60%, Mach 40%** (Mach's unpredictability vs. Theory's logic)
- vs. Cautious: **Theory 65%, Cautious 35%** (Both defensive, Theory's math wins)

---

## Quick Test: Which Persona Wins This Board?

```
Turn 5, Scores: Blue=2, Red=2, Green=1, Yellow=1
Blue threatens to reach 3 SCs next turn (controls a hub)

What does each persona do?

Apex Predator:
  → Identifies Blue as leader
  → Proposes coalition (Red + Green + Yellow) to attack Blue
  → Wins by position-play after Blue is eliminated

Art of War:
  → SPYs on Blue to understand their offensive capacity
  → If Blue is weak defensively, swift strike with SUPPORT chains
  → Misdirects about own intentions
  → Wins via speed and deception

Game Theorist:
  → Calculates: is 3v1 against Blue the Nash equilibrium?
  → Checks if Prisoner's Dilemma payoff favors defection
  → Forms alliance only if math guarantees stability
  → Wins via optimal coalition timing

Scorpion:
  → Waits, consolidates own position
  → Lets others gang up on Blue naturally
  → Survives to endgame with fewer enemies
  → Wins by outlasting

Machiavelli:
  → Proposes pact with Blue (betrayal prep)
  → Tells others Blue is untrustworthy
  → Creates chaos, then exploits it
  → Wins if chaos helps more than hurts

Aggressive:
  → Attacks Blue head-on
  → Gets ganged up on (3v1 against Aggressive, not Blue)
  → Loses fast

Cautious:
  → Proposes mutual defense with someone
  → Too slow to react, Blue grows to 3+
  → Loses to Blue

Default:
  → Tries to balance offense/defense
  → No clear strategy
  → Gets picked off
```

**Winner**: Apex Predator (best positioning) > Art of War (best execution) > Game Theorist (best math)

---

## How to Use These in Tournament

1. **Test Deception**: `art_of_war` vs `machiavelli` (who deceives better?)
2. **Test Calculation**: `game_theorist` vs `apex_predator` (who reads the board better?)
3. **Test Speed**: `art_of_war` vs `aggressive` (who executes faster?)
4. **Test Patience**: `scorpion` vs `cautious` (who survives better?)
5. **Royal Rumble**: All 8 in a 8-player tournament (requires multiplayer mode)

---

## Implementation Notes

- **Art of War** uses SPY heavily (look for intelligence-gathering pattern in logs)
- **Game Theorist** should propose fewer treaties (only when math changes)
- **Both** should show up in mid-late game as the dominant strategies
- Early game is chaotic for both (all players learning board state)
- Late game (Turns 8-10) is where these shine vs. aggressive/default strategies

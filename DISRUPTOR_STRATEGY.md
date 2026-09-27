# Disruptor Persona: The Game Changer

## Philosophy
**"Deny rivals, don't compete."**

While others fight over empty supply centers, Disruptor attacks their existing ones. It's asymmetric warfare disguised as diplomacy.

---

## Core Strategy

### The Insight
When **Red** and **Blue** are both eyeing **Centerlands**, Disruptor doesn't fight them for it. Instead, Disruptor attacks **Red's Northreach** (home SC).

**Result**: 
- Red has to defend home or lose it → can't contest Centerlands
- Blue claims Centerlands → grows stronger
- But Blue is now the leader → gets ganged up on
- Disruptor gains by weakening Red without expending units

### Attack Pattern

```
Turn 1-2: Identify competing factions
Turn 3-5: Attack their HOME supply centers (Northreach, Ironpeaks, Sunport, Duneport)
Turn 6-10: Consolidate, let chaos play out, claim remaining undefended SCs
```

---

## Priority Order (Disruption First)

1. **SCAN**: Which factions are both competing for the same empty SC?
2. **ATTACK**: Strike the most dangerous competitor in THEIR home territory
3. **SUPPORT**: Defend your own SCs (minimum required)
4. **IGNORE**: Empty SCs unless completely undefended (free wins only)
5. **SPY**: On whoever looks strongest before attacking their core

---

## Expected Matchups

| vs. | Result | Why |
|-----|--------|-----|
| **Apex Predator** | Disruptor wins (40-50%) | Apex builds coalitions; Disruptor breaks them by weakening coalition members |
| **Art of War** | Draw (45-55%) | Both use SPY; Disruptor's disruption vs. War's speed = coin flip |
| **Game Theorist** | Apex wins (40-60%) | Theory tries to calculate optimal move; Disruptor's chaos disrupts math |
| **Aggressive** | Disruptor wins (55-60%) | Aggressive overextends; Disruptor picks off weakened SC |
| **Machiavelli** | Disruptor wins (60%) | Machiavelli betrays; Disruptor disrupts before betrayal happens |
| **Cautious** | Disruptor wins (65%) | Cautious too slow; Disruptor already destroyed their SC |
| **Scorpion** | Disruptor wins (50-55%) | Disruption breaks Scorpion's patient strategy |

---

## Disruptor vs. Others: Complete Breakdown

### 1. Disruptor vs. Apex Predator (60-70 minute game)

**Turn 1-2**:
- Apex builds coalition (Blue + Yellow) to stop Red
- Disruptor sees this: attacks Blue's Ironpeaks

**Turn 3-4**:
- Blue has to defend home → weakens coalition
- Apex's coalition falls apart
- Disruptor has weakened one player without joining conflict

**Turn 5-10**:
- Now it's a free-for-all (no stable coalition)
- Disruptor picks up pieces from the chaos
- **Result**: Disruptor 40-45% win rate vs. Apex 50-55%

### 2. Disruptor vs. Art of War (Speed + Deception Duel)

**Turn 1-3**:
- Art of War SPYs heavily on all rivals
- Disruptor identifies who's fighting
- Both move simultaneously

**Turn 4-7**:
- Art of War executes swift SUPPORT chains
- Disruptor interrupts by hitting their HOME SC
- Race condition: who attacks first?

**Expected**: **50-50 split** (speed vs. disruption = pure tempo)

### 3. Disruptor vs. Scorpion (Patience vs. Urgency)

**Turn 1-5**:
- Scorpion waits, consolidates empty SCs slowly
- Disruptor attacks aggressive neighbors
- Scorpion looks secure

**Turn 6-10**:
- Scorpion's safe position + 2-3 SCs
- Other factions weakened by Disruptor
- Scorpion wins endgame

**Result**: Scorpion 50%, Disruptor 45% (Scorpion's patience beats disruption)

---

## Why Disruptor Breaks Stalemates

Current tournament shows many **4-way ties** because defensive alliances form naturally:
- Everyone defends their home
- No one can reach 5 SCs
- Turn 10 stalemate

**Disruptor changes this by**:
1. Breaking the "mutual defense" assumption
2. Attacking undefended SCs while allies are busy defending
3. Creating asymmetric threats (I'll take yours instead of yours)
4. Forcing difficult choices (defend home or contest empty SC?)

---

## Disruptor Communication Strategy

Messages are threats, not promises:
- ❌ "Let's ally against Red" (Machiavelli)
- ✓ "While you fight each other, I take what's yours" (Disruptor)

All messages under 25 words, focused on intimidation and misdirection.

**Example messages**:
- "Distracted by Centerlands? Ironpeaks falls tonight."
- "Watch your backs. Your SCs are mine."
- "While you fight, I rebuild. Your turn next."

---

## Recommended Tournament Matchup

Test the chaos:
```bash
python3 tournament_runner.py \
  --prompt-names "disruptor,apex_predator,art_of_war,scorpion"
```

**Expected outcome**:
1. Disruptor breaks alliances → chaos
2. Apex tries to recover → fails, tied with Disruptor
3. Art of War rides chaos → clean 40-50% win rate
4. Scorpion waits out disruption → steady 50%+

---

## Weaknesses of Disruptor

| Weakness | Why | Mitigation |
|----------|-----|-----------|
| No offensive initiative | Always reacting to others' fights | SPY on leaders, pre-empt attacks |
| Can't reach 5 SCs solo | Doesn't claim empty ones aggressively | Requires chaos to create openings |
| Slow early game | Takes time to identify targets | Focus on high-value home SCs (Centerlands) |
| Predictable pattern | Experienced players see "attack home" coming | Mix in empty SC captures |

---

## Strengths of Disruptor

| Strength | Why | Impact |
|----------|-----|--------|
| Breaks symmetry | Attacks existing instead of empty | Forces hard choices on enemies |
| Denies resources | Weakens coalition members | Coalition collapses |
| Low risk | Targets already-contested regions | Easy retreats if overwhelmed |
| Psychological | "Your SC is mine" is scary | Shifts focus away from you |
| Ends deadlock | Forces action in stalemate situations | Creates opening for endgame |

---

## Game Arc: Disruptor Wins

```
[Start]
  Apex: Building coalition vs. Aggressive
  Art of War: Spying on leaders
  Scorpion: Consolidating empty SCs
  Disruptor: Waiting, analyzing

[Turn 3]
  → Disruptor attacks Aggressive's home (Duneport)
  → Aggressive panics, defends
  → Apex coalition benefits (Aggressive weaker)
  → Disruptor weakens the emerging leader

[Turn 6]
  → Apex and Aggressive fight over Southvale
  → Disruptor doesn't join, attacks Apex's Northreach
  → Apex: "Wait, we had a coalition!"
  → Disruptor: "Not anymore."

[Turn 9]
  → Board is chaos (no clear leader)
  → Disruptor has 3 SCs (Northreach, Sunport, Centerlands)
  → Scorpion has 2 SCs (by being patient)
  → Everyone else has 1 SC

[Turn 10]
  → Disruptor claims Duneport (undefended, everyone busy)
  → Disruptor reaches 4 SCs
  → Scorpion reaches 3 SCs
  → RESULT: Scorpion wins (closest to 5)
  → Or Disruptor gets lucky and reaches 5
```

---

## Summary

**Disruptor** is the **wildcard** persona:
- Not trying to win directly (like Apex)
- Not trying to be tactical (like Art of War)
- Not trying to calculate (like Game Theorist)
- Just **disrupting everyone else's plans**

In a tournament full of planning and coalitions, Disruptor thrives on **chaos**. Every time two opponents fight, Disruptor weakens one. Every time an alliance forms, Disruptor breaks it by attacking a member.

**Best case**: Ends a 4-way stalemate, creates opening for Disruptor to reach 5 SCs.
**Typical case**: Breaks alliances, creates chaos, Scorpion wins from attrition.
**Worst case**: Gets isolated and attacked on all fronts.

---

## Total Persona Count: 11

1. **Apex Predator** 🦁 — Board analysis + coalition timing
2. **Art of War** ⚔️ — Deception + speed (Sun Tzu)
3. **Game Theorist** 📊 — Nash Equilibrium + expected value
4. **Scorpion** 🦂 — Patient endgame dominance
5. **Disruptor** ⚡ — Denial + asymmetric attack (NEW)
6. **Machiavelli** 😈 — Betrayal as theater
7. **Aggressive** ⚔️ — Blunt constant pressure
8. **Cautious** 🛡️ — Defensive stability
9. **Default** 📋 — Balanced baseline
10. machiavelli_fox_lion — Fox/lion duality
11. machiavelli_opportunist — Ruthless opportunism

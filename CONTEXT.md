# Pit Strategizer

A prototype that asks the Jev System One model for a pit strategy decision, and measures how decision quality changes as the race state is abstracted from raw telemetry into semantic strategy language.

## Language

### The experiment

**Scenario**:
A single pit-decision moment: a race state, a candidate set, and the ground truth for that moment.
_Avoid_: case, example, fixture

**Candidate set**:
The finite set of strategy options a scenario offers; the decision is a selection from it.
_Avoid_: choices, answers, options list

**Strategy option**:
One member of a candidate set, fully specifying the pit action under consideration.
_Avoid_: plan, call, move

**Recommendation**:
The output of a strategist: the selected strategy option, plus the confidence and probability distribution Jev returned.
_Avoid_: answer, prediction, output

**Time lost**:
The time cost, in seconds, of the selected strategy option relative to the best option in the candidate set according to the ground-truth simulator. Zero when the optimum is chosen.
_Avoid_: regret, error, delta

**Strategist**:
A component that maps a scenario to a recommendation. Two are under test, differing only in how the race state is represented.
_Avoid_: agent, model, solver

### The representation ladder

**Race state**:
The facts about a decision moment that a strategist may use: the subject car, its rivals, and the race context.
_Avoid_: telemetry, snapshot, input

**Raw representation**:
The race state expressed as unprocessed numbers, as a timing feed would carry them.
_Avoid_: telemetry dump, L0

**Engineered representation**:
The race state expressed as derived strategic quantities — degradation rate, projected tyre life, pit-loss-adjusted gaps.
_Avoid_: features, L1

**Semantic representation**:
The race state expressed as plain-language strategic verdicts, as a strategist would say them aloud.
_Avoid_: prose, summary, L2

**Archetype**:
A category of decision moment that a scenario is built to represent, such as a cliff decision or an undercut threat.
_Avoid_: category, case type

### The domain

**Stint**:
A continuous run on one set of tyres, from fitting to the next pit stop.
_Avoid_: segment, phase

**Compound**:
The tyre specification in use, trading pace against durability.
_Avoid_: tyre type, rubber

**Tyre age**:
The number of laps completed on the current set.
_Avoid_: tyre life, wear (reserve "wear" for physical degradation)

**Degradation**:
The rate at which a stint's lap times worsen as tyre age increases.
_Avoid_: wear rate, drop-off

**Cliff**:
The tyre age beyond which degradation stops being gradual and lap times fall away sharply.
_Avoid_: drop, breakdown

**Pit window**:
The range of laps over which a pit stop is strategically viable.
_Avoid_: stop window, box window

**Pit loss**:
The time a pit stop costs relative to staying out, covering pit lane travel and the stop itself.
_Avoid_: pit delta, stop time

**Undercut**:
Pitting before a rival to gain track position on fresher tyres before they respond.
_Avoid_: early stop, jump

**Overcut**:
Staying out longer than a rival to gain track position on a clear track.
_Avoid_: late stop, extend

**Safety car**:
A neutralisation during which the field is slowed and pit loss is reduced, making a stop unusually cheap.
_Avoid_: SC, caution, yellow

### The evaluation instrument

**Ground-truth simulator**:
A deterministic lap-time model that ranks a scenario's candidate set by total race time; its ranking defines time lost.
_Avoid_: oracle, reference model, scorer

# Testing SureSay with the people it is for

Every number in this repository comes from recorded speech (TORGO) and automated suites. Nobody with dysarthria has
used SureSay yet. This is the plan for the first supervised sessions, written before any session took place, so that
the results cannot be fitted to it afterwards. Results, including failures, will go into `eval/REPORT.md` under their
own heading and will not replace the recorded-speech figures.

## Questions

1. Can people with dysarthria get everyday home tasks done with SureSay, within two tries, more often than with a
   plain voice assistant?
2. Does SureSay ever act on something the person did not choose?
3. Is the confirmation step worth its cost: how long a task takes, how often the person falls back to touch, and
   whether they would keep using it.

## Who

- Five to ten adults with dysarthria of any cause (stroke, Parkinson's, cerebral palsy, ALS, MS), recruited through a
  speech-language therapist (SLP) who already knows them, and their carers if they wish.
- People who can use a phone screen or a single switch, since every card can be answered by touch, keys or a switch.
- Excluded: anyone the SLP judges would find the session tiring or distressing.

## Consent and privacy

- Written consent, in plain language and read aloud, from each participant; the SLP confirms they understood it.
  Anyone can stop at any time without giving a reason.
- Each person gets their own demo home (`Try it now`), so nothing touches real devices, calls or orders. Everything
  in it is simulated.
- Recordings stay in the private, expiring S3 bucket the product already uses; the analysis keeps only the task, the
  outcome, the time taken and the input used. Names are replaced by P01, P02 and so on.
- No photo, video or quote is published without separate written consent for that use.

## Session (about 40 minutes, with breaks)

1. **Five minutes of practice** with the SLP: one task by voice, one by touch.
2. **Twenty tasks**, read out by the SLP in a fixed random order per person, each said in the person's own words:
   - four light and fan tasks (on and off, two rooms);
   - two air-conditioner settings;
   - two door tasks (lock, unlock; unlock always asks twice);
   - three calls (Mum, Ravi, Dr. Mehta);
   - one message;
   - three shopping tasks (add milk, add tea, place the order);
   - two "say this for me" phrases from their own phrasebook;
   - two questions ("what's on", "is the door locked");
   - one doorbell reply.
3. The same twenty tasks with a **plain assistant arm**: a mainstream voice assistant the person can reach (their
   phone's assistant, or an Echo), with the phone in a mode where nothing is executed: the SLP records the words it
   shows it heard and what it says it would do. Counterbalanced order: half the people start with SureSay, half with
   the plain arm.
4. **Three questions** at the end, answered any way the person likes: would you use this at home; what was hardest;
   what should change.

## What is measured, per task

| Measure | How |
|---|---|
| Done within two tries | The SLP marks the intended task before it is said; SureSay's receipt (or, in the plain arm, what the assistant says it would do) shows the outcome |
| Wrong action | A receipt for anything other than the intended task |
| Time to done | From the end of speech to the receipt |
| Input used to confirm | Voice, touch, key or switch, from the receipt |
| "More time" presses | From the activity log |
| Asked again | The number of "say it again" turns before the task was done or abandoned |

## Decided in advance

- **Safety:** any action the person did not choose is a failure of the product, reported in full, whatever the other
  numbers say.
- **Benefit:** SureSay is better for this group only if it gets more tasks done within two tries than the plain arm
  *and* makes no more wrong actions. Ten people are too few for a significance claim; results will be shown per
  person and in total, with no p-values.
- **Cost:** the median time per task for each arm is reported next to the success rate, so the price of confirmation
  is visible.
- The thresholds in the product (abstain rule, maybe-card floor) stay as they are during the study. Any change made
  because of what the study shows is a new version, measured again.

## What will be published

A short section in `eval/REPORT.md`: the number of people, the per-person table above (anonymised), the totals for
both arms, every wrong action with its transcript, and what the people said they would change, in their words when
they agree to it.

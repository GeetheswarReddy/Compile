# Compile

Compile is an adaptive coding-practice experience for placement preparation. It serves questions only after their reference solution has been verified against their test cases.

## Learning

**Anonymous Learner**:
The stable, unauthenticated demo participant whose progress is retained by their browser-generated identity.
_Avoid_: User, account, candidate

**Learner Quota**:
The Demo Quota share assigned to one Anonymous Learner: five Run & Check actions and two generation requests before their controls become read-only.
_Avoid_: Per-user limit

**Topic**:
A practice domain—Arrays, Strings, or Hash Maps/Two Pointers—with its own calibration and question pool.
_Avoid_: Category, subject

**Mastery**:
An Anonymous Learner's 1–10 ability estimate within one Topic, distinct from Question Difficulty Score.
_Avoid_: Score, skill level

**Mastery Confidence**:
The system's confidence in a Topic's Mastery estimate; requesting a Hint lowers it without changing a correct attempt into an incorrect one.
_Avoid_: Hint penalty

**Mastery Update**:
The clamped one-point increase or decrease to Topic Mastery after, respectively, a correct or incorrect submission.
_Avoid_: Difficulty stepping

**Target Difficulty**:
The Question Difficulty Score equal to the current Topic Mastery; Compile serves the nearest unattempted Question if none has that exact score.
_Avoid_: Recommended level

**Scored Attempt**:
The first Run & Check verdict for an Anonymous Learner and Question; only this verdict changes Mastery. Later checks are feedback-only.
_Avoid_: Final submission

**Baseline Assessment**:
The mandatory-once-per-browser fixed five-question calibration sequence—Arrays and Strings Questions at scores 3 and 6, and one Hash Maps/Two Pointers Question at score 5—that establishes initial per-Topic Mastery.
_Avoid_: Quiz, onboarding test

**Baseline Resume Point**:
The first unanswered Baseline Assessment Question for an Anonymous Learner who returns after leaving the sequence.
_Avoid_: Restarted baseline

**Prepared Question**:
A Generated Question verified asynchronously after a Generation Timeout and retained for the Anonymous Learner's next attempt only when it is within one point of their then-current Target Difficulty.
_Avoid_: Prefetched question

**Read-Only Demo State**:
The state after the Demo Quota is exhausted, in which prior learning material, hints, recordings, and the Demo Trace remain viewable but execution and generation are unavailable.
_Avoid_: Outage, locked demo

## Questions

**Question**:
A single-language (Python) named-function coding exercise with typed parameters, a return value, a Difficulty Score, constraints, a reference solution, and executable test cases.
_Avoid_: Problem, challenge

**Verified Question**:
A Question whose reference solution executes successfully against all of its test cases and whose required structure and constraints are valid.
_Avoid_: Proven question, guaranteed question

**Hidden Test**:
An executable test case for a Question whose input and expected output are not shown to the Learner; each Question has two or three.
_Avoid_: Private test

**Seeded Question**:
A Verified Question curated in the initial topic corpus. Each Topic's ten Seeded Questions comprise three scores 1–3, four scores 4–7, and three scores 8–10.
_Avoid_: Static question, fallback question

**Generated Question**:
A Verified Question produced for a Learner's current Mastery and grounded in the Seeded Question corpus. It must be materially distinct from Seeded and previously served Questions in its Topic.
_Avoid_: AI question, LLM question

**Provenance**:
Whether a served Question is Seeded or Generated.
_Avoid_: Source, origin

**Curated Question**:
The learner-facing label for a Seeded Question served after the generation pipeline falls back.
_Avoid_: Fallback question

**Difficulty Score**:
An integer from 1 (easiest) to 10 (hardest) that compares Seeded and Generated Questions within a Topic.
_Avoid_: Level, tier, band

**Medium-Difficulty Question**:
A Question with a Difficulty Score from 4 through 7, inclusive.
_Avoid_: Medium question

**Demo Trace**:
The visible, per-attempt account of question provenance, verification retries, and the learner's Mastery snapshot in the demonstration build.
_Avoid_: Agent trace panel, debug log

**Technique Tag**:
A spoiler-sensitive label for the approach a Question uses. It is the only learner-facing tag and is hidden until the Learner chooses to reveal it.
_Avoid_: Topic tag, difficulty tag

**Demo Mode**:
The demonstration presentation in which the Demo Trace is visible; it is hidden in a future real-user experience.
_Avoid_: Debug mode

**Execution Service**:
The external sandbox that runs Python submissions and Question reference solutions under fixed resource limits.
_Avoid_: Compiler, Judge

**Submission Verdict**:
The learner-facing outcome of a code submission: a pass/fail summary with no more than two failed-case inputs and expected-versus-actual outputs.
_Avoid_: Test report

**Run & Check**:
The sole learner execution action, which evaluates a Question's tests and produces a Submission Verdict and Mastery Update.
_Avoid_: Run, submit

**Completed Topic**:
A Topic for which an Anonymous Learner has attempted every available Seeded and Prepared Question; Compile does not repeat or endlessly generate more Questions in the demo.
_Avoid_: Exhausted topic

**Generation Timeout**:
An eight-second wait for a Generated Question before Compile serves the closest Seeded Question instead.
_Avoid_: Loading timeout

**Demo Quota**:
The manual-reset demo-wide ceiling of 40 Execution Service submissions and 20 generation attempts, after which Compile fails closed.
_Avoid_: Rate limit, monthly limit

**Generation Failure**:
The learner-visible failure of all three generation candidates for one Topic, resulting in a Curated Question and one increment to that Topic's failure counter.
_Avoid_: Retry failure

**Stale Generation**:
A verified Generated Question whose Difficulty Score is no longer within one point of the Learner's Target Difficulty when it becomes available; it is not a Generation Failure.
_Avoid_: Invalid generation

**Verification Record**:
The stored result of validating a Seeded Question before deployment; it accompanies the Question and is not rerun merely to open the demo.
_Avoid_: Test artifact

**Reflection Recording**:
An optional, private browser-recorded audio note linked to one Anonymous Learner and one Question after a pass/fail submission, for later recall. Only one may exist per Learner and Question; a replacement overwrites the prior recording.
_Avoid_: Voice note, recording

**Reflection Retention**:
The 30-day lifetime of a Reflection Recording, with an immediate deletion control for the Learner.
_Avoid_: Archive policy

**Reflection Replacement**:
The learner-confirmed deletion of the existing Reflection Recording for a Question before a new recording is saved.
_Avoid_: Overwrite

**Reflection Card**:
The per-attempted-Question control for playing, replacing, or deleting its Reflection Recording.
_Avoid_: Recordings page

**Recording Consent**:
The first-use notice that a Reflection Recording is private to the browser identity, can be deleted immediately, and expires after 30 days.
_Avoid_: Microphone prompt

**Hint Ladder**:
The four learner-requested assistance levels for a Question, ending in the full reference solution; no level is revealed automatically after a pass or failure.
_Avoid_: Solution reveal

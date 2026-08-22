# Foothold - Pathfinders Write-Up

Category: Overcoming Obstacles.
Finalized 2026-08-20; the body below is the submission text for the form's description field (500-word cap; this text is 464 words).
The form has a separate "Tools used" field; that text is in the last section of this file.

---

Every year about 80,000 Californians transfer from a community college to a UC or CSU.
The GAO found that transfer students lose, on average, 43 percent of their credits.
Half of them are on Pell grants, so lost credits are lost aid money on top of lost time.
The rules that decide what transfers are public.
They sit in articulation agreements on ASSIST.org, thousands of them, and almost nobody reads them before applying.

Foothold reads them.

A student picks their community college, their target university, and their major, then pastes in their courses straight from the portal.
Foothold checks every course against the official articulation agreement, line by line, and lays the verdicts out on a wall: transfers cleanly, at risk, no articulation, plus what they still owe for the major, in units and dollars.
Click any verdict and it shows the citation.
In the demo, a De Anza student headed to UC San Diego for computer science finds nine units of C++ worth nothing (the agreement wants the Java path) and an assembly-language series she is two-thirds through, which today counts as zero.
Caught now, that is about a $340 fix at De Anza.
Caught after transfer, it is a $15,686 quarter at UCSD.

Then the part I am proudest of.
Foothold drafts her credit appeal, and a validator rejects any draft that cites a course or agreement fact not in the deterministic findings.
She is not asking for a favor; she is pointing at the university's own agreement.
A second tab serves students already enrolled at a university: which community-college courses articulate back to your degree, ranked by dollars saved.

Tools in this space exist.
Transferology, TES, and ASSIST itself are lookup tables that assume you already know what to look up.
Foothold starts from the student: transcript in, appeal letter out.
And where Stellic audits degrees for institutions, Foothold sits upstream, student-side, before the application is ever filed.

One rule shaped the whole build: the AI never decides what transfers.
The agreement does.
Verdicts come from a deterministic evaluator over 31,236 agreements and 352,024 articulation rows, covering 115 community colleges into all nine UCs and the six largest CSUs, with over 950 automated tests behind it.
Claude drafts exactly one thing in the product, the letter's prose, and even that is validated against the findings, with a plain template as fallback.
A student who appeals with a wrong citation is worse off than one with no letter at all.
That is why.

The interface draws the transfer as a climbing wall the student is already partway up.
Every verdict reads as shape, icon, and word, never color alone.

Expansion is mechanical: every state keeps equivalency tables, one adapter away from the same evaluator, wall, and letter.

Built solo in three weeks.

---

## Tools used (form field)

Claude Code (Fable 5) for development, Claude Design for UI, Claude in Chrome for testing, Claude API (claude-sonnet-5) in-product, ElevenLabs for voiceover, CapCut for editing and auto-captions, Screen Studio for screen recording, and Fly.io for hosting.

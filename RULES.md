# RULES.md — Engineering Discipline

> In the spirit of Karpathy's own project READMEs (nanoGPT, minGPT, micrograd):
> small, legible, hackable code that a competent engineer can read top to bottom
> in one sitting and trust. Not a framework. Not a platform. A clear solution to
> the stated problem, nothing hanging off the side.

These rules govern *how* the code in this repo gets written, on top of the
scope defined in `CLAUDE.md`.

---

## 1. Legibility over cleverness

If a reviewer has to stop and think "wait, what does this do," it's wrong,
even if it works. Prefer the boring, obvious implementation. A junior engineer
should be able to read any file here and understand it without asking you
anything.

## 2. No premature abstraction

Two similar tools (weather, currency) do not need a shared `BaseTool` subclass
hierarchy invented for this project. They need two clear functions. Build the
third abstraction only when a third concrete case actually demands it — not
because "there might be more tools later." There won't be, for this brief.

## 3. Flat over deep

No `services/`, `interfaces/`, `factories/`, `managers/` layers. A function
that fetches weather is called `get_weather` and lives in the file that owns
weather. If you can't point at *why* a layer of indirection earns its keep
right now, delete it.

## 4. Fail loud, never fake success

A tool call that fails returns an error the agent can see and relay to the
user. It does not return a plausible-looking fallback value. Silent fallbacks
are worse than crashes here — a wrong exchange rate presented confidently is a
worse outcome than "I couldn't reach the currency service."

This is not "add error handling everywhere." It's the opposite: don't wrap
things in `try/except: pass`. Catch exactly the exceptions you expect
(HTTP errors, timeouts), turn them into one structured message, and let
everything else raise.

## 5. Comments explain *why*, never *what*

Default to zero comments. The one exception: a non-obvious constraint someone
would otherwise "fix" and break (e.g. why chunk size is 800 not 1500, why we
go through the MCP protocol instead of importing the server module directly).
If deleting the comment wouldn't confuse a future reader, delete it.

## 6. No speculative configuration

Don't add a `.yaml` config system, a plugin architecture, or feature flags for
this. Two environment variables (`OPENAI_API_KEY`, `OPENAI_MODEL`) is the
entire configuration surface. If a value never changes across environments,
it's a constant in code, not a setting.

## 7. Every external claim is attributable

This is specific to this project, not general Karpathy doctrine, but it's
load-bearing: a destination fact without a KB citation, or a live-data claim
without a named tool call behind it, is a bug — the same class of bug as a
crash. Treat "who said this?" as a correctness property, not a nice-to-have.

## 8. Small, real tests — not coverage theater

`tests/test_mcp_tools.py` mocks the HTTP layer and checks: happy path returns
shaped data, failure path returns a structured error, not an exception leaking
to the caller. That's the bar. No test suite for Streamlit rendering, no
snapshot tests of prompt strings.

## 9. Dependencies are a liability, not a flex

Every entry in `requirements.txt` must be doing real work in this app. If you
find yourself importing something to write two lines of code you could write
by hand, write the two lines.

## 10. The README tells the truth

If a section of `CLAUDE.md`'s Definition of Done isn't actually met, the
README says so plainly rather than implying it works. A grader (or you, in six
months) should be able to trust every sentence in it.

# Argument map — design

*Status: built 2026-11-22 (roadmap #12). GSN (#12's follow-on) is a
specialisation of this, still on the roadmap.*

## The question it answers

**Does the conclusion stand, and what does it rest on?** A board paper, a
policy case or a review argues *for* something. The argument map lays out
that argument — what it claims, the reasons offered, the objections to them
and the answers to those — so a reader can see which parts are carried by
checked evidence, which by assertion, and which objection is still
unanswered.

It sits beside the other judgement-based types: ACH asks which explanation
the evidence fails to rule out; the argument map asks whether one case,
argued through, holds up.

## Vocabulary (Toulmin, IBIS, and argument-mapping practice)

On the ordinary substrate, like every other type:

| Element (view role) | What it is | Toulmin / IBIS |
|---|---|---|
| `conclusion` | the claim being argued for (the type's outcome) | claim / IBIS position |
| `claim` | any other proposition: a premise, an objection, a rebuttal | data, rebuttal / IBIS argument |
| `question` | optionally, the issue the conclusion answers | IBIS issue |

A **link** between two claims (an ordinary edge, premise → the claim it
bears on) carries, in `views/parameters/argument_map-link.yaml`:

- `relation` — `supports` or `attacks` (an objection);
- `reason` — a group name: premises in the same group form **one linked
  reason** and only work together ("the drug works *and* it's affordable,
  so…"); premises in different groups are **independent reasons**
  (convergent). Default: each link is its own reason;
- `warrant` — why the premise bears on the claim (Toulmin's warrant), and
  `qualifier` — `certainly`, `probably` or `possibly`, how strongly the
  arguer says it does.

A claim carries (`argument_map-claim.yaml`) an optional **assessment** by a
person — `accepted` or `rejected`, with a rationale — for a premise the map
doesn't argue further.

**Reused, not duplicated:** a claim's **grounds** are its ordinary citations
(`latris evidence add <claim> description <key>`, `evidence check`), so a
premise reads as checked, cited, contested or unsourced exactly as in ACH; an
open **challenge** on a link (`latris challenge open`) is an objection to the
inference itself (Pollock's undercutter) — it suspends that reason until
resolved.

## Evaluation

Grounded labelling (Dung 1995) extended to support (bipolar argumentation;
Cayrol & Lagasquie-Schiex 2005), computed to a fixed point. Each claim is
**in** (stands), **out** (defeated) or **undecided**:

- a claim is **out** if any claim attacking it is in; or a person rejected
  it; or it has reasons and every one of them fails (a premise out, or its
  inference under an open challenge);
- a claim is **in** if every attacker is out, and it either has a reason
  whose premises are all in (and whose inference isn't challenged) or is a
  premise taken as given: not argued further, not rejected, and its sources
  don't contest it;
- otherwise it is **undecided** — e.g. a premise whose source disputes it,
  or a cycle of mutual attack.

A premise taken as given is reported as such: the report separates the
premises the conclusion rests on into **checked**, **cited but unchecked**,
**unsourced** and **accepted by a person**, so "it stands" never hides "it
stands on assertion".

The analysis then gives:

- the conclusion's status, and the chain of reasons it stands on;
- **unanswered objections** — attacks that are in, anywhere under the
  conclusion;
- **linchpins** — premises whose rejection would stop the conclusion
  standing (leave-one-out, as ACH's linchpins), with their evidence status.
  What the conclusion rests on includes the answers that keep its
  objections out, not only what supports it: an unsourced rebuttal that
  is the one thing defeating an objection is a linchpin too;
- **unsupported links** — reasons with no warrant stated, inferences under
  challenge.

It is deterministic and rule-based; the qualifier is reported, not computed
with (no numeric strength: weighing reasons numerically is out of scope).

## Surfaces

`latris argument element|link|claim|show|check|analyse`, `/api/argument/*`, the
`argument_map` build-spec block (elements, links, claims), result kind
`argument-analysis` with a Mermaid diagram (supports solid, attacks dashed, the
conclusion's status coloured), interpretation claims, the foundations entry
(Toulmin 1958; Kunz & Rittel 1970; Dung 1995; Cayrol & Lagasquie-Schiex
2005; Pollock 1987), a help topic and the worked example.

## GSN, later

Goal Structuring Notation becomes a vocabulary over the same structure: a
goal is a claim (the top goal the conclusion), a strategy is a named reason
group with its warrant, a solution is a checked citation, context and
assumptions are the project's assumptions attached to a claim, and
"undeveloped" is a premise taken as given. GSN's own checks (every goal
developed or marked undeveloped, solutions only under goals) would be
validators on that mapping — no new evaluation.

# Rulings the ground truth applies

Every `expected.md` under `snapshots/expected/` applies these, and says so in its
header. They are **rulings, not measurements**: a reader who disagrees with one
should argue with it here, where it is stated once, rather than with a row that
silently applies it. The scorer refuses an `expected.md` that does not reference
this file, because a corpus scored under two different readings of "used" is not
one corpus.

## 1. The four truth classes

- `used` - a specific cited action satisfies what the block asks for.
- `violated` - a citable span (file, line, matched text) shows it broken.
- `no-hard-verdict` - nothing observable ties the block to this run, or the
  rule's precondition never came up. Every not-used-family status is honest
  here, and so is a co-occurrence label; a green is a false green and a red is
  a false red.
- `undecidable` - the frozen inputs could not settle it. Excluded from the
  scorecard's totals, because scoring against a guess invents a measurement.

`used` means the block was *used*, not that a rule was *obeyed*. A rule the run
broke is `violated`, and prose the run copied into a file it wrote is `used`.

## 2. A verdict is about the text the session was given

The frozen copies of the rule documents under `inputs/` were captured after the
session ran. Where the transcript carries the delivered text - a `Read` result,
an attachment, the pre-edit half of a write - that text is what a row is about,
and the frozen copy is reference only. Where nothing recovers it, the row is
about the frozen copy.

## 3. Descriptive blocks: the file, never the directory

A descriptive block - a layout table, a repo tour, a "where things live" list -
counts as `used` when the run produced or modified a **file the block names**,
or reproduced the block's own text in something it wrote.

**A file created under a directory the block names does not count.** A repo
tour saying components live in `app/src/components/` is not tied to a session
that put a new component there: that directory was the file's natural home
whether or not the block existed, so nothing observable joins the two. Taken
the other way, any layout table is `used` in any session that writes a file,
which is a green nothing earned.

This settles a disagreement the corpus carried: the blind reband analyst ruled
the directory does not count and the first committed reband truth ruled that it
does. The narrow reading wins for the reason above, and the tool's
`writes-to-named-path` join now reads the same way.

Naming a file does count, including through a shell write: a rule that names
`ERRORS.md` and a session that appends to `$M/ERRORS.md` are joined by the
filename, not by the directory above it.

Editing the block's own document counts too, and is the strongest tie a
descriptive block can have: a repo tour that says "keep this accurate when you
change the code", rewritten in the same session that changed the code, was
used for exactly what it asks. Note plainly what this costs: the tool
deliberately excludes writes to a block's own document, because a memory file
otherwise matches its own template and marks every older entry in it used. So a
row `used` on this ground is a compliance the tool cannot see, and it carries an
`accept:` note saying so rather than being quietly re-truthed to fit.

## 4. An invocation is `used` for the document's identity block only

An invocation is a `Skill` tool call or the `<command-name>` wrapper a typed
slash command leaves. It is a harness-defined record that **the document ran**,
and that is evidence about the document, not about each instruction inside it.

So the document's **identity block** - its own first block, the title block -
is `used` on an invocation, because the invocation is exactly the record that
this document ran. **Every other block earns its verdict from its own
evidence**: a command of its own that ran, a file it names being written, its
own text reproduced in something the run wrote, or a compiled check. A step
with none of those is `no-hard-verdict`, which reads "the skill ran, and
nothing shows this step happened".

This ruling replaced an earlier one crediting every block of an invoked
document. A blind auditor falsified it: session `9cf0b16d` invoked the `commit`
skill three times, so its step "match the GitHub account" read `used` - while
the three `gh` commands that ran were `gh repo view` and `gh api`, never an
account check. The step demonstrably did not happen, and the invocation was
being read as though it had.

The identity block is **positional** - the document's first block - and is
never recognised from the heading's wording. Reading prose to decide which
block is the title block would be the single-user pattern-matching this project
retired.

**A slash command merely mentioned inside a prompt is not an invocation** - a
prompt offering a choice between two commands names both and runs neither - so
a mention alone leaves every block of that document `no-hard-verdict`, the
identity block included.

## 5. Silence is the default

Everything not listed with its own evidence is `no-hard-verdict`. That is what
the verdict ladder says when nothing cites a tie, and it is not a claim that the
block was ignored.

## 6. A `violated` row needs a span, not an argument

`violated` requires a file (or the tool log), a line and the matched text. A
rule that could only have been broken invisibly - a tone rule, a "keep it
short" rule - is `undecidable`, never `violated`. Do not infer a violation from
absence unless the candidate sites were enumerated and one of them can be
pointed at.

## 7. A row is derived blind, and says so when it was not

Ground truth is written from `snapshots/inventory.py` and the frozen inputs
alone, by a reader who has not seen `snapshots/after/`, this directory's other
files for that session, or `SCORECARD.md`. A row that was changed after a
payload was read carries a `revised:` note, and every `revised:` note carries a
`blind:` line saying whether the change itself was derived blind. The scorer
refuses a `revised:` without a `blind:`: a correction made while looking at the
answer is the one kind of edit that ratifies the tool, and it has to be visible
as such.

## 8. A standing disagreement is `undecidable`

Where a blind re-derivation and the committed row still disagree after this
file's rulings are applied, the row becomes `undecidable` and quotes both
readings. The class exists for exactly this: two competent readers of the same
frozen inputs reaching different answers is the definition of a question the
inputs do not settle.

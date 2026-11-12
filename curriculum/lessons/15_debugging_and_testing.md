# Module 15 — Debugging and unittest: fix it, then prove it

## Why this matters for Linux+

Troubleshooting is 28% of the Linux+ exam. The methodology is always the same:

1. Observe the symptom.
2. Form a hypothesis.
3. Test the smallest thing that can confirm or refute it.
4. Fix the cause, not the symptom.
5. Prove the fix and prevent regression.

This module applies that method to a buggy Python module and then makes you
write tests that would have caught the bug.

## The buggy module

The lab provides `netmask.py`, which converts between CIDR prefixes and
dotted-quad netmasks:

```python
prefix_to_mask(24)   # should be "255.255.255.0"
mask_to_prefix("255.255.255.0")  # should be 24
```

It has two bugs. Your job is to find them with evidence, not by guessing.

## Reading a traceback (again)

```text
Traceback (most recent call last):
  File "netmask.py", line 17, in <module>
    print(prefix_to_mask(24))
          ^^^^^^^^^^^^^^^^^^^
  File "netmask.py", line 12, in prefix_to_mask
    mask = (0xFFFFFFFF << (31 - prefix)) & 0xFFFFFFFF
ValueError: ...
```

Read bottom-up: exception type, message, failing operation, callers. The
traceback tells you *where*, not *why*. The why comes from testing values.

## Print debugging, done well

Bad:

```python
print("here")
print(x)
```

Better: print the inputs, the intermediate value, and the expected value.

```python
prefix = 24
mask = (0xFFFFFFFF << (31 - prefix)) & 0xFFFFFFFF
print(f"{prefix=} {mask=:#010x} expected=0xffffff00")
```

Python 3.8+ f-string debugging (`{expr=}`) prints the expression and its value.
It is the fastest way to inspect a loop or a branch.

## `pdb`: the standard debugger

Run a script under the debugger:

```bash
python3 -m pdb netmask.py
```

Or drop into it at a line:

```python
breakpoint()      # Python 3.7+
```

Common commands:

| Command | Meaning |
|---|---|
| `l` / `list` | show source around the current line |
| `n` / `next` | step over the next line |
| `s` / `step` | step into a function |
| `c` / `continue` | run to the next breakpoint |
| `p expr` | print an expression |
| `pp expr` | pretty-print |
| `b file:line` | set a breakpoint |
| `w` / `where` | show the call stack |
| `q` / `quit` | quit |

Use `pdb` when you need to inspect state across several lines. Use `print` for
one-off checks. Use tests to lock in the fix.

## Binary and bit arithmetic

The bug is a classic off-by-one:

```python
mask = (0xFFFFFFFF << (31 - prefix)) & 0xFFFFFFFF
```

For `/24`, shifting by 7 instead of 8 produces `255.255.255.128`. For `/0`,
`31 - 0 = 31` produces `0xFFFFFFFE`, not `0.0.0.0`. Boundary values expose
off-by-one bugs that common values may hide.

Test boundaries:

```text
/0  0.0.0.0
/8  255.0.0.0
/16 255.255.0.0
/24 255.255.255.0
/25 255.255.255.128
/30 255.255.255.252
/32 255.255.255.255
```

The inverse has a different bug: counting zero bits instead of one bits.

```python
return bits.count("0")   # wrong
return bits.count("1")   # right
```

Again, a boundary (`0.0.0.0`, `255.255.255.255`) makes it obvious.

## `unittest` basics

```python
import unittest
from netmask import prefix_to_mask


class TestPrefixToMask(unittest.TestCase):
    def test_common_prefixes(self):
        self.assertEqual(prefix_to_mask(24), "255.255.255.0")

    def test_invalid_prefix(self):
        with self.assertRaises(ValueError):
            prefix_to_mask(33)


if __name__ == "__main__":
    unittest.main()
```

Run:

```bash
python3 -m unittest -q test_netmask.py
python3 -m unittest discover -s . -p 'test_*.py' -v
```

Assertions:

| Method | Checks |
|---|---|
| `assertEqual(a, b)` | `a == b` |
| `assertNotEqual(a, b)` | `a != b` |
| `assertTrue(x)` / `assertFalse(x)` | truth value |
| `assertIn(a, container)` | membership |
| `assertRaises(Exc)` | exception raised (context manager) |
| `assertAlmostEqual(a, b)` | floats within 7 places |
| `assertIsNone(x)` | identity |

Each test method should test one behaviour and have a name that describes it.
`test_24` is less useful than `test_prefix_24_is_class_c`.

## Test the contract, not the implementation

Good tests assert what callers rely on:

```python
self.assertEqual(prefix_to_mask(24), "255.255.255.0")
```

Bad tests assert internal details:

```python
self.assertEqual(netmask._LAST_SHIFT, 8)   # brittle
```

If you refactor the implementation, the contract tests should still pass. That
is the point.

## Edge cases and invalid input

For this module, cover:

- `prefix_to_mask` for `/0`, `/8`, `/16`, `/24`, `/25`, `/32`,
- `mask_to_prefix` for the same masks (round trip),
- invalid prefixes `-1`, `33` raise `ValueError`,
- non-contiguous masks (`255.255.255.1`) raise `ValueError`,
- malformed masks (`abc`, `300.1.1.1`, missing octets) raise `ValueError`.

Why test invalid input? Because callers will pass it. A function that silently
returns nonsense is worse than one that raises.

## Mutation thinking

A test suite is only as good as the bugs it catches. The verifier runs your
tests against the **original buggy module**. If your tests still pass, they do
not detect the bug.

This is called mutation testing: introduce a known fault and check that the
suite fails. You do not need a framework to use the idea. Ask:

> If I change this line to a plausible wrong value, does a test fail?

If not, add a test.

## Debugging checklist

1. Reproduce reliably. Write down the exact command and input.
2. Reduce the case. Find the smallest input that fails.
3. Read the error, not just the last line.
4. Check assumptions with `print`/`pdb`: types, values, lengths.
5. Change one thing at a time.
6. Re-run the failing case, then the whole suite.
7. Add a regression test before moving on.

## Guided walkthrough

```bash
cd "$(python3 main.py doctor | sed -n 's/^  \[ok\] Lab: //p' | head -1)" 2>/dev/null || true
mkdir -p 15_debug_and_test
cd 15_debug_and_test
```

Observe the bugs:

```bash
python3 - <<'PY'
import netmask
for prefix in (0, 8, 16, 24, 25, 32):
    try:
        print(prefix, netmask.prefix_to_mask(prefix))
    except Exception as exc:
        print(prefix, "raised", exc)
for mask in ("0.0.0.0", "255.255.255.0", "255.255.255.255"):
    try:
        print(mask, netmask.mask_to_prefix(mask))
    except Exception as exc:
        print(mask, "raised", exc)
PY
```

Use the debugger on the failing call:

```bash
python3 -m pdb -c continue -c 'p netmask.prefix_to_mask(24)' netmask.py 2>/dev/null || true
```

Or add `breakpoint()` inside `prefix_to_mask` temporarily.

Fix both functions, then write `test_netmask.py`. Run it:

```bash
python3 -m unittest -q test_netmask.py
```

Deliberately re-break the module (`31 - prefix`) and confirm your tests fail.
Then restore the fix. That is the mutation check the verifier performs.

Verify:

```bash
python3 main.py verify 15
```

## Common mistakes

| Mistake | Result | Fix |
|---|---|---|
| Fixing the symptom (`if prefix == 24: return ...`) | other prefixes still wrong | fix the formula |
| Tests only the example from the prompt | bug survives elsewhere | boundaries and invalid input |
| Tests that assert the buggy value | suite “passes” but is wrong | assert the contract |
| Catching exceptions in the test | hides failures | let the test fail |
| No assertions | test always passes | assert something meaningful |
| Testing private internals | brittle | test public behaviour |
| Not running the whole suite after a fix | regression | run all tests |
| Debugging by random edits | slow, no evidence | reproduce, reduce, inspect |

## Mission checklist

- [ ] `15_debug_and_test/netmask.py` has both bugs fixed.
- [ ] `prefix_to_mask` handles `/0` through `/32`, including `/25`.
- [ ] `mask_to_prefix` is the inverse for valid masks.
- [ ] Invalid prefixes raise `ValueError`.
- [ ] Non-contiguous/malformed masks raise `ValueError`.
- [ ] `test_netmask.py` has at least four test methods.
- [ ] The suite passes against the fixed module.
- [ ] The suite fails against the original buggy module (mutation check).

Then run:

```bash
python3 main.py verify 15
```

## Extra practice

1. Add `assertAlmostEqual` tests for an `address_in_subnet()` helper.
2. Use `subTest` to loop over prefixes in one test method.
3. Run coverage with `python3 -m trace --count` or install `coverage`.
4. Add a property-style test: for every prefix 0–32, round-trip the mask.
5. Write a second buggy version with a different fault and confirm your tests
   catch it too.
6. Try `pytest` if you want fixtures and parametrization, but keep the
   standard-library suite working.

## Call variations, replayed (`debugassist eval replay-variants`)

The call-variation check (`DA_CALL_VARIANTS`, no model) run on each real case's upstream fix and on the last fix of every earlier run of it (diffs from the run cassettes, which are local), set against upstream's regression test. `test_pass_check_fail` would be a false alarm; `test_fail_check_pass` a narrow fix the check misses.

| case | calls | upstream_fix | fixes | test_pass_check_pass | test_fail_check_fail | test_pass_check_fail | test_fail_check_pass |
|---|---|---|---|---|---|---|---|
| REAL-001 | 3 | pass | 14 | 0 | 14 | 0 | 0 |
| REAL-002 | 1 | pass | 6 | 6 | 0 | 0 | 0 |
| REAL-003 | 2 | pass | 3 | 3 | 0 | 0 | 0 |
| REAL-004 | 5 | pass | 5 | 5 | 0 | 0 | 0 |
| REAL-005 | 2 | pass | 6 | 6 | 0 | 0 | 0 |


| case | arm | seed | upstream_test | check | spellings | first_mismatch |
|---|---|---|---|---|---|---|
| REAL-001 | real-04ab2bf | 1 | False | fail | 9 | `Example.value(self=example, number=3)` (through the class, keyword arguments) gives ('raises', 'TypeError'); `example.value(3)` gives ('ok', "'6'") |
| REAL-001 | real-04ab2bf | 2 | False | fail | 9 | `Example.value(self=example, number=3)` (through the class, keyword arguments) gives ('raises', 'TypeError'); `example.value(3)` gives ('ok', "'6'") |
| REAL-001 | real-04ab2bf | 3 | False | fail | 9 | `Example.value(self=example, number=3)` (through the class, keyword arguments) gives ('raises', 'TypeError'); `example.value(3)` gives ('ok', "'6'") |
| REAL-001 | fixwidth-7f15556 | 2 | False | fail | 9 | `Example.value(self=example, number=3)` (through the class, keyword arguments) gives ('raises', 'TypeError'); `example.value(3)` gives ('ok', "'6'") |
| REAL-001 | fixwidth-7f15556 | 3 | False | fail | 9 | `Example.value(self=example, number=3)` (through the class, keyword arguments) gives ('raises', 'TypeError'); `example.value(3)` gives ('ok', "'6'") |
| REAL-001 | fixwidth-7f15556 | 4 | False | fail | 9 | `Example.value(self=example, number=3)` (through the class, keyword arguments) gives ('raises', 'TypeError'); `example.value(3)` gives ('ok', "'6'") |
| REAL-001 | repro2-f277379 | 1 | False | fail | 9 | `Example.value(self=example, number=3)` (through the class, keyword arguments) gives ('raises', 'TypeError'); `example.value(3)` gives ('ok', "'6'") |
| REAL-001 | repro2-f277379 | 2 | False | fail | 9 | `Example.value(self=example, number=3)` (through the class, keyword arguments) gives ('raises', 'TypeError'); `example.value(3)` gives ('ok', "'6'") |
| REAL-001 | repro2-f277379 | 3 | False | fail | 9 | Example.value vs example.value: __wrapped__: <cachetools._cachedmethod._unlocked.<locals>.Descriptor.Wrapper object> through the class, <function Example.value> through the instance |
| REAL-001 | callers-0ed427d | 1 | False | fail | 9 | `Example.value(self=example, number=3)` (through the class, keyword arguments) gives ('raises', 'TypeError'); `example.value(3)` gives ('ok', "'6'") |
| REAL-001 | callers-0ed427d | 2 | False | fail | 9 | `Example.value(self=example, number=3)` (through the class, keyword arguments) gives ('raises', 'TypeError'); `example.value(3)` gives ('ok', "'6'") |
| REAL-001 | callers-0ed427d | 3 | False | fail | 9 | `Example.value(self=example, number=3)` (through the class, keyword arguments) gives ('raises', 'TypeError'); `example.value(3)` gives ('ok', "'6'") |
| REAL-001 | variants-4b1325c | 1 | False | fail | 9 | Example.value vs example.value: __wrapped__: <cachetools._cachedmethod._unlocked.<locals>.Descriptor.Wrapper object> through the class, <function Example.value> through the instance |
| REAL-001 | variants-4b1325c | 2 | False | fail | 9 | `Example.value(self=example, number=3)` (through the class, keyword arguments) gives ('raises', 'TypeError'); `example.value(3)` gives ('ok', "'6'") |
| REAL-001 | variants-4b1325c | 3 | False | unchecked | 0 |  |
| REAL-002 | real-16088da | 1 | True | pass | 1 |  |
| REAL-002 | real-16088da | 2 | True | pass | 1 |  |
| REAL-002 | real-16088da | 3 | True | pass | 1 |  |
| REAL-002 | fixwidth-7f15556 | 1 | True | pass | 1 |  |
| REAL-002 | fixwidth-7f15556 | 2 | True | pass | 1 |  |
| REAL-002 | fixwidth-7f15556 | 3 | True | pass | 1 |  |
| REAL-003 | real-16088da | 2 | True | pass | 2 |  |
| REAL-003 | real-16088da | 3 | True | pass | 2 |  |
| REAL-003 | fixwidth-7f15556 | 3 | True | pass | 2 |  |
| REAL-004 | real-16088da | 1 | True | pass | 5 |  |
| REAL-004 | real-16088da | 2 | True | pass | 5 |  |
| REAL-004 | real-16088da | 3 | True | pass | 5 |  |
| REAL-004 | fixwidth-7f15556 | 1 | True | pass | 5 |  |
| REAL-004 | fixwidth-7f15556 | 3 | True | pass | 5 |  |
| REAL-005 | real-16088da | 1 | True | pass | 2 |  |
| REAL-005 | real-16088da | 2 | True | pass | 2 |  |
| REAL-005 | real-16088da | 3 | True | pass | 2 |  |
| REAL-005 | fixwidth-7f15556 | 1 | True | pass | 2 |  |
| REAL-005 | fixwidth-7f15556 | 2 | True | pass | 2 |  |
| REAL-005 | fixwidth-7f15556 | 3 | True | pass | 2 |  |

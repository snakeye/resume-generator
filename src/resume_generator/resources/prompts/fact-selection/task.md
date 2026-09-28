Select the strongest relevant evidence from the JSON payload in the next message
and supplement each position to its configured minimum with useful unmatched
facts. Passthrough language, education, and work skill matches are already
covered and should not be selected. Do not rewrite facts. For every matched
selected fact, `covers` must be copied from evidence matches containing that
exact fact path, even when the same match also contains a work skill path. Supplemental
facts must use `covers: []`. Do not return `uncovered`; it is computed after
selection from all selected and passthrough evidence.

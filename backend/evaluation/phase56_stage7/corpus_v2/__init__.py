"""The `dynatutor-ko-corpus-v2.0-candidate` contract, additive to v1.

Nothing in this package changes the frozen v1 corpus, the v1 loader, the v1
schema, or the official strict score.  v2 is a *candidate* contract with its own
records, validator, migration, projection and shadow runner, and a v1 record
only becomes a v2 record through an explicit migration that a human-authored
manifest drives.  There is no automatic upgrade, and the shadow score this
package produces is never the official score.
"""

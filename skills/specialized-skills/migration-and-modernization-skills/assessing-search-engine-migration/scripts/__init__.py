"""Migration assessment helpers.

Stdlib-only. The skill's three CLIs live here:

* ``decision_engine.py`` — Service-vs-Serverless and migration-path rules.
* ``pricing_estimator.py`` — sizing math and monthly cost estimation.
* ``source_assessor.py`` — profile validation and final report rendering.

All three import from :mod:`scripts.common` for shared types and helpers.
"""

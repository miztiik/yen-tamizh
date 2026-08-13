"""yen-tamizh backend: build-time puzzle generators and data pipeline.

Runs only in CI or locally (Holy Law #1): it ingests corpora, generates and
validates puzzles, and bakes the bank + assets into ``frontend/public/``. It is
never a runtime server and is never imported by frontend code.
"""

__version__ = "0.1.0"

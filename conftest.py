# Anchors pytest's rootdir at the repo root so it's added to sys.path,
# letting `tests/` import `app` without needing `python -m pytest` or a
# PYTHONPATH override.

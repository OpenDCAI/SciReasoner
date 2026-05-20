"""Offline smoke tests — verify that the thin shell wires up correctly without
hitting any API. The competition pipeline at seephys_pro_codabench/scripts/run_v2.py
must be importable, and the core symbols must be exported on scireasoner's API.
"""

import importlib
import sys


def test_package_importable():
    pkg = importlib.import_module("scireasoner")
    for name in ("solve", "caption", "reason", "critic", "Result"):
        assert hasattr(pkg, name), f"scireasoner.{name} missing"


def test_competition_pipeline_imported():
    """Confirm the thin shell successfully imported run_v2 from the
    competition codebase without modifying it."""
    import scireasoner.pipeline as p
    assert hasattr(p, "_run_v2"), "pipeline did not import run_v2"
    rv = p._run_v2
    for name in ("stage_caption", "stage_reason", "stage_critic", "make_client"):
        assert hasattr(rv, name), f"run_v2.{name} not found via thin shell"


def test_l1_fewshot_prompt_present():
    """sub_008 added REASONER_USER_L1_FEWSHOT — confirm it survived round-trip."""
    import scireasoner.pipeline as p
    assert hasattr(p._run_v2, "REASONER_USER_L1_FEWSHOT")


def test_l4_caption_template_present():
    """sub_004 added L4_CAPTION_USER — confirm it survived."""
    import scireasoner.pipeline as p
    assert hasattr(p._run_v2, "L4_CAPTION_USER")


def test_args_namespace_minimal():
    """_build_args should produce a namespace with all the fields stage_* read."""
    from scireasoner.pipeline import _build_args
    args = _build_args()
    for required in (
        "caption_model", "reason_model", "critic_model",
        "use_critic", "k_samples", "sc_temperature",
        "max_tokens", "timeout", "max_retries",
    ):
        assert hasattr(args, required), f"_build_args missing {required}"


def test_image_loader_path():
    """_load_image_to_dict accepts a path that exists."""
    import tempfile, os as _os
    from scireasoner.pipeline import _load_image_to_dict
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"x" * 16)
        tmp_path = f.name
    try:
        d = _load_image_to_dict(tmp_path)
        assert d is not None
        assert d["bytes"].startswith(b"\x89PNG")
    finally:
        _os.unlink(tmp_path)


def test_image_loader_none():
    from scireasoner.pipeline import _load_image_to_dict
    assert _load_image_to_dict(None) is None

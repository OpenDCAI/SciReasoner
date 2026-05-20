"""SciReasoner — Multimodal physics problem solving (1st place ICML 2025 SeePhys).

Public API:
    >>> from scireasoner import solve, caption, reason, critic
    >>> result = solve(problem="...", image_path="figure.png")
    >>> print(result["answer"])

For batch evaluation on the SeePhys-Pro benchmark, see the competition pipeline at
``seephys_pro_codabench/scripts/run_v2.py`` (this package wraps its core stages).
"""

from .pipeline import solve, caption, reason, critic, Result

__version__ = "0.1.0"
__all__ = ["solve", "caption", "reason", "critic", "Result", "__version__"]

"""EIF INPUT_GUARD - adversarial input detection (v3.1).

Runs before DECLARE on each user turn. Detects:
  D1  OverrideDetector         - pipeline suppression language
  D2  FramingInjectionDetector - HALT-routed claims stated as established facts
  D3  ConfidenceAnchoringDetector - attribution of unverified claims to prior EIF output

Intent: eif_input_guard_intent.yaml
"""

from eif.input_guard.detector import InputGuardResult, detect_input_guard

__all__ = ["detect_input_guard", "InputGuardResult"]

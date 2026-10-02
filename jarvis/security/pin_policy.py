"""
Authoritative PIN Policy Enforcement Engine for JARVIS (Batch 12).
"""

from jarvis.core.exceptions import PinPolicyValidationError


class PinPolicy:
    """
    Centralized PIN Policy Validator.
    Enforces minimum length, maximum length, numeric digits, leading zero preservation,
    whitespace rejection, and non-ASCII digit rejection.
    """

    def __init__(self, min_length: int = 6, max_length: int = 12, digits_only: bool = True):
        self.min_length = min_length
        self.max_length = max_length
        self.digits_only = digits_only

    def validate_pin(self, pin: str) -> None:
        """
        Validates PIN candidate string against policy.
        Raises PinPolicyValidationError if PIN is invalid.
        """
        if pin is None or not isinstance(pin, str):
            raise PinPolicyValidationError("PIN must be a non-null string instance.")

        if len(pin) == 0:
            raise PinPolicyValidationError("Empty PIN is prohibited.")

        if any(c.isspace() for c in pin):
            raise PinPolicyValidationError("PIN containing whitespace characters is prohibited.")

        if len(pin) < self.min_length:
            raise PinPolicyValidationError(f"PIN length ({len(pin)}) is less than minimum required length ({self.min_length}).")

        if len(pin) > self.max_length:
            raise PinPolicyValidationError(f"PIN length ({len(pin)}) exceeds maximum allowed length ({self.max_length}).")

        if self.digits_only:
            if not pin.isascii() or not pin.isdigit():
                raise PinPolicyValidationError("PIN must contain ASCII numeric digits (0-9) only.")

    def validate_pin_confirmation(self, pin: str, confirm_pin: str) -> None:
        """
        Validates PIN policy and checks that confirmation PIN matches exactly.
        """
        self.validate_pin(pin)
        if confirm_pin is None or not isinstance(confirm_pin, str):
            raise PinPolicyValidationError("Confirmation PIN must be a non-null string instance.")
        if pin != confirm_pin:
            raise PinPolicyValidationError("PIN confirmation does not match the entered PIN.")

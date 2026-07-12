class PhysicsUserInputError(Exception):
    """Base class for expected, client-correctable physics input failures."""


class PhysicsDomainError(PhysicsUserInputError):
    """A supplied value violates an explicitly validated physics domain."""


class PhysicsClarificationError(PhysicsUserInputError):
    """A clarification choice or value payload is invalid."""

import pytest
from jarvis.core.exceptions import (
    JarvisError,
    ConfigurationError,
    AuthorizationError,
    ResourceLimitError,
)


def test_exception_hierarchy():
    err = ConfigurationError("Config value missing")
    assert isinstance(err, JarvisError)

    err2 = ResourceLimitError("Memory limit exceeded")
    assert isinstance(err2, JarvisError)

    with pytest.raises(JarvisError):
        raise AuthorizationError("Access denied")

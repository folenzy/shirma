import pytest

from shirma.detect import Detector
from shirma.policy import Policy
from shirma.vault import Vault


@pytest.fixture(scope="session")
def detector() -> Detector:
    d = Detector()
    d.ner.warm_up()
    return d


@pytest.fixture
def vault(detector: Detector) -> Vault:
    return Vault(detector, Policy())

import pytest
from os import environ
import datetime  # noqa: I251
from typing import Any, List, Optional, Tuple, Type, Dict, MutableMapping, Optional, Sequence

from dlt.common import Decimal, pendulum
from dlt.common.configuration.container import Container
from dlt.common.configuration.specs.config_providers_context import ConfigProvidersContext
from dlt.common.typing import TSecretValue, StrAny
from dlt.common.configuration import configspec
from dlt.common.configuration.providers import Provider
from dlt.common.configuration.specs import BaseConfiguration, CredentialsConfiguration, RunConfiguration


@configspec
class WrongConfiguration(RunConfiguration):
    pipeline_name: str = "Some Name"
    NoneConfigVar: str = None
    log_color: bool = True


@configspec
class CoercionTestConfiguration(RunConfiguration):
    pipeline_name: str = "Some Name"
    str_val: str = None
    int_val: int = None
    bool_val: bool = None
    list_val: list = None  # type: ignore
    dict_val: dict = None  # type: ignore
    bytes_val: bytes = None
    float_val: float = None
    tuple_val: Tuple[int, int, StrAny] = None
    any_val: Any = None
    none_val: str = None
    COMPLEX_VAL: Dict[str, Tuple[int, List[str], List[str]]] = None
    date_val: datetime.datetime = None
    dec_val: Decimal = None
    sequence_val: Sequence[str] = None
    gen_list_val: List[str] = None
    mapping_val: StrAny = None
    mutable_mapping_val: MutableMapping[str, str] = None


@configspec
class SecretConfiguration(BaseConfiguration):
    secret_value: TSecretValue = None


@configspec
class SecretCredentials(CredentialsConfiguration):
    secret_value: TSecretValue = None


@configspec
class WithCredentialsConfiguration(BaseConfiguration):
    credentials: SecretCredentials


@configspec
class NamespacedConfiguration(BaseConfiguration):
    __namespace__ = "DLT_TEST"

    password: str = None


@pytest.fixture(scope="function")
def environment() -> Any:
    environ.clear()
    return environ


@pytest.fixture(scope="function")
def mock_provider() -> "MockProvider":
    container = Container()
    with container.injectable_context(ConfigProvidersContext()) as providers:
        # replace all providers with MockProvider that does not support secrets
        mock_provider = MockProvider()
        providers.providers = [mock_provider]
        yield mock_provider


class MockProvider(Provider):

    def __init__(self) -> None:
        self.value: Any = None
        self.return_value_on: Tuple[str] = ()
        self.reset_stats()

    def reset_stats(self) -> None:
        self.last_namespace: Tuple[str] = None
        self.last_namespaces: List[Tuple[str]] = []

    def get_value(self, key: str, hint: Type[Any], *namespaces: str) -> Tuple[Optional[Any], str]:
        self.last_namespace = namespaces
        self.last_namespaces.append(namespaces)
        print("|".join(namespaces) + "-" + key)
        if namespaces == self.return_value_on:
            rv = self.value
        else:
            rv = None
        return rv, "|".join(namespaces) + "-" + key

    @property
    def supports_secrets(self) -> bool:
        return False

    @property
    def supports_namespaces(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "Mock Provider"


class SecretMockProvider(MockProvider):
    @property
    def supports_secrets(self) -> bool:
        return True


COERCIONS = {
    'str_val': 'test string',
    'int_val': 12345,
    'bool_val': True,
    'list_val': [1, "2", [3]],
    'dict_val': {
        'a': 1,
        "b": "2"
    },
    'bytes_val': b'Hello World!',
    'float_val': 1.18927,
    "tuple_val": (1, 2, {"1": "complicated dicts allowed in literal eval"}),
    'any_val': "function() {}",
    'none_val': "none",
    'COMPLEX_VAL': {
        "_": [1440, ["*"], []],
        "change-email": [560, ["*"], []]
    },
    "date_val": pendulum.now(),
    "dec_val": Decimal("22.38"),
    "sequence_val": ["A", "B", "KAPPA"],
    "gen_list_val": ["C", "Z", "N"],
    "mapping_val": {"FL": 1, "FR": {"1": 2}},
    "mutable_mapping_val": {"str": "str"}
}
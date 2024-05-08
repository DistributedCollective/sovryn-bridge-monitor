from time import sleep
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Collection,
    Type,
)

from requests.exceptions import (
    ConnectionError,
    HTTPError,
    Timeout,
    TooManyRedirects,
)

from web3.types import (
    RPCEndpoint,
    RPCResponse,
)

if TYPE_CHECKING:
    from web3 import Web3  # noqa: F401

from web3.middleware.exception_retry_request import check_if_retry_on_failure


# Forked, add sleep

def exception_retry_middleware(
    make_request: Callable[[RPCEndpoint, Any], RPCResponse],
    web3: "Web3",
    errors: Collection[Type[BaseException]],
    retries: int = 10,
) -> Callable[[RPCEndpoint, Any], RPCResponse]:
    """
    Creates middleware that retries failed HTTP requests. Is a default
    middleware for HTTPProvider.
    """
    def middleware(method: RPCEndpoint, params: Any) -> RPCResponse:
        if check_if_retry_on_failure(method):
            for i in range(retries):
                try:
                    return make_request(method, params)
                # https://github.com/python/mypy/issues/5349
                except errors as e:  # type: ignore
                    if i < retries - 1:
                        sleep_time = i ** 2
                        print("Got exception", e, f", retrying in {sleep_time}s...")
                        sleep(sleep_time)
                        continue
                    else:
                        raise
            return None
        else:
            return make_request(method, params)
    return middleware


def http_retry_request_middleware(
    make_request: Callable[[RPCEndpoint, Any], Any], web3: "Web3"
) -> Callable[[RPCEndpoint, Any], Any]:
    return exception_retry_middleware(
        make_request,
        web3,
        (ConnectionError, HTTPError, Timeout, TooManyRedirects)
    )

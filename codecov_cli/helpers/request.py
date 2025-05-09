import json
import logging
from sys import exit
from time import sleep
from typing import Optional

import click
import requests

from codecov_cli import __version__
from codecov_cli.types import RequestError, RequestResult

logger = logging.getLogger("codecovcli")

MAX_RETRIES = 3

USER_AGENT = f"codecov-cli/{__version__}"


def _set_user_agent(headers: Optional[dict] = None) -> dict:
    headers = headers or {}
    headers.setdefault("User-Agent", USER_AGENT)
    return headers


def patch(url: str, headers: dict = None, json: dict = None) -> requests.Response:
    headers = _set_user_agent(headers)
    return requests.patch(url, json=json, headers=headers)


def get(url: str, headers: dict = None, params: dict = None) -> requests.Response:
    headers = _set_user_agent(headers)
    return requests.get(url, params=params, headers=headers)


def put(url: str, data: dict = None, headers: dict = None) -> requests.Response:
    headers = _set_user_agent(headers)
    return requests.put(url, data=data, headers=headers)


def post(
    url: str,
    data: Optional[dict] = None,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
) -> requests.Response:
    headers = _set_user_agent(headers)
    return requests.post(url, json=data, headers=headers, params=params)


def backoff_time(curr_retry):
    return 2 ** (curr_retry - 1)


class RetryException(Exception): ...


def retry_request(func):
    def wrapper(*args, **kwargs):
        retry = 0
        while retry < MAX_RETRIES:
            try:
                response = func(*args, **kwargs)
                if response.status_code >= 500:
                    logger.warning(
                        f"Response status code was {response.status_code}.",
                        extra=dict(extra_log_attributes=dict(retry=retry)),
                    )
                    raise RetryException
                return response
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                RetryException,
            ):
                logger.warning(
                    "Request failed. Retrying",
                    extra=dict(extra_log_attributes=dict(retry=retry)),
                )
                sleep(backoff_time(retry))
                retry += 1
        raise Exception(f"Request failed after too many retries. URL: {kwargs.get('url', args[0] if args else 'Unknown')}")

    return wrapper


@retry_request
def send_post_request(
    url: str,
    data: Optional[dict] = None,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
):
    return request_result(post(url=url, data=data, headers=headers, params=params))


@retry_request
def send_get_request(
    url: str, headers: dict = None, params: dict = None
) -> RequestResult:
    return request_result(get(url=url, headers=headers, params=params))


def get_token_header_or_fail(token: Optional[str]) -> dict:
    """
    Rejects requests with no Authorization token. Prevents tokenless uploads.
    """
    if token is None:
        raise click.ClickException(
            "Codecov token not found. Please provide Codecov token with -t flag."
        )
    return {"Authorization": f"token {token}"}


def get_token_header(token: Optional[str]) -> Optional[dict]:
    """
    Allows requests with no Authorization token.
    """
    if token is None:
        return None
    return {"Authorization": f"token {token}"}


@retry_request
def send_put_request(
    url: str,
    data: dict = None,
    headers: dict = None,
):
    return request_result(put(url=url, data=data, headers=headers))


def request_result(resp: requests.Response) -> RequestResult:
    if resp.status_code >= 400:
        return RequestResult(
            status_code=resp.status_code,
            error=RequestError(
                code=f"HTTP Error {resp.status_code}",
                description=resp.text,
                params={},
            ),
            warnings=[],
            text=resp.text,
        )

    return RequestResult(
        status_code=resp.status_code, error=None, warnings=[], text=resp.text
    )


def log_warnings_and_errors_if_any(
    sending_result: RequestResult, process_desc: str, fail_on_error: bool = False
):
    logger.info(
        f"Process {process_desc} complete",
    )
    logger.debug(
        f"{process_desc} result",
        extra=dict(
            extra_log_attributes=dict(result=_sanitize_request_result(sending_result))
        ),
    )
    if sending_result.warnings:
        number_warnings = len(sending_result.warnings)
        pluralization = "s" if number_warnings > 1 else ""
        logger.info(
            f"{process_desc} process had {number_warnings} warning{pluralization}",
        )
        for ind, w in enumerate(sending_result.warnings):
            logger.warning(f"Warning {ind + 1}: {w.message}")
    if sending_result.error is not None:
        logger.error(f"{process_desc} failed: {sending_result.error.description}")
        if fail_on_error:
            exit(1)


def _sanitize_request_result(result: RequestResult):
    if not hasattr(result, "text"):
        return result

    try:
        text_as_dict = json.loads(result.text)
        token = text_as_dict.get("repository").get("yaml").get("codecov").get("token")
        if token:
            sanitized_token = str(token)[:1] + 18 * "*"
            text_as_dict["repository"]["yaml"]["codecov"]["token"] = sanitized_token
            sanitized_text = json.dumps(text_as_dict)

            return RequestResult(
                status_code=result.status_code,
                error=result.error,
                warnings=result.warnings,
                text=sanitized_text,
            )
    except (AttributeError, json.JSONDecodeError):
        pass

    return result

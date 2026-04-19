import datetime
from dataclasses import dataclass
from typing import Optional, Union

import aiohttp
import requests


@dataclass(frozen=True)
class AGOLUserPass:
    """ArcGIS Online credentials used to mint short-lived tokens."""

    username: str
    password: str


def get_token(username: str, password: str) -> dict:
    """Synchronously request an ArcGIS Online token."""
    url = "https://www.arcgis.com/sharing/rest/generateToken"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "f": "json",
        "client": "requestip",
        "username": username,
        "password": password,
    }
    return requests.post(url, headers=headers, data=data, timeout=30).json()


@dataclass
class ArcGISTokenSession:
    """
    Wrap an aiohttp session with ArcGIS token refresh behavior.

    The wrapped session still performs the actual requests; this helper only
    injects auth headers/body params and refreshes tokens when needed.
    """

    session: aiohttp.ClientSession
    credentials: Optional[AGOLUserPass] = None
    token_url: str = "https://www.arcgis.com/sharing/rest/generateToken"
    token_refresh_threshold: int = 60
    token: Optional[str] = None
    expires: Optional[Union[int, float]] = None

    @property
    def token_request_payload(self) -> dict:
        """Return the payload for the token request."""
        if self.credentials is None:
            raise ValueError("Credentials are required to generate a token.")
        return {
            "f": "json",
            "client": "requestip",
            "username": self.credentials.username,
            "password": self.credentials.password,
        }

    @property
    def auth_headers(self) -> dict[str, str]:
        """Return authentication headers with the token if available."""
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def update_headers(self, headers: Optional[dict] = None) -> dict:
        """Return headers merged with the active token."""
        request_headers = dict(headers or {})
        request_headers.update(self.auth_headers)
        return request_headers

    def update_dict(self, input_dict: Optional[dict] = None) -> dict:
        """Return a request payload/query dict merged with the active token."""
        output_dict = dict(input_dict or {})
        if self.token and "token" not in output_dict:
            output_dict["token"] = self.token
        return output_dict

    async def update_token(self) -> None:
        """Update the token by making a request to the token URL."""
        async with self.session.post(
            self.token_url,
            data=self.token_request_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        self.token = data["token"]
        self.expires = data["expires"]

    def token_needs_update(self) -> bool:
        """Check if the token needs to be updated."""
        if self.credentials is None:
            return False
        if not self.token or not self.expires:
            return True
        expires_at = self.expires / 1000 if self.expires > 1e11 else self.expires
        expires_dt = datetime.datetime.fromtimestamp(
            expires_at,
            tz=datetime.timezone.utc,
        )
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        return (expires_dt - now_dt).total_seconds() < self.token_refresh_threshold

    async def update_token_if_needed(self) -> None:
        """Ensure the token is valid and refresh if necessary."""
        if self.token_needs_update():
            await self.update_token()

    async def get(
        self,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Make a GET request to the specified URL with the token."""
        await self.update_token_if_needed()
        request_headers = (
            self.update_headers(
                headers,
            )
            if "token" not in (params or {})
            else dict(headers or {})
        )
        request_params = self.update_dict(params)
        return await self.session.get(
            url,
            params=request_params,
            headers=request_headers,
            **kwargs,
        )

    async def post(
        self,
        url: str,
        data: Optional[dict] = None,
        headers: Optional[dict] = None,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Make a POST request to the specified URL with the token."""
        await self.update_token_if_needed()
        request_headers = (
            self.update_headers(
                headers,
            )
            if "token" not in (data or {})
            else dict(headers or {})
        )
        request_data = self.update_dict(data)
        return await self.session.post(
            url,
            data=request_data,
            headers=request_headers,
            **kwargs,
        )

    async def __aenter__(self) -> "ArcGISTokenSession":
        """Enter the runtime context related to this object."""
        await self.update_token_if_needed()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """Exit the runtime context related to this object."""
        return None

"""Bounded loopback-only model transport, without proxies or redirects."""
import ipaddress
import json
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Model endpoint redirects are disabled")


def validate_endpoint(endpoint):
    parsed = urlparse(endpoint)
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = False
    if not loopback or parsed.scheme != "http" or parsed.username or parsed.password:
        raise ValueError("Model endpoint must use a numeric loopback HTTP address")
    return endpoint


def post_json(endpoint, payload, timeout=60):
    validate_endpoint(endpoint)
    request = Request(endpoint, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        data = response.read(4 * 1024 * 1024 + 1)
    if len(data) > 4 * 1024 * 1024:
        raise RuntimeError("Model response exceeds configured limit")
    return json.loads(data)

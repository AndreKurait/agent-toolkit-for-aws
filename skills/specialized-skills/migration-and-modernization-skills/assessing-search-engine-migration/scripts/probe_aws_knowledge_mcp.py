#!/usr/bin/env python3
"""Probe the AWS Knowledge MCP server for every tool this skill depends on.

Run this whenever you suspect schema drift or want to confirm the live
retrieval recipes in references/knowledge-retrieval.md still work.

Stdlib-only. No auth required.

Exit code 0 = all six tools answered successfully (or returned an
expected, well-formed error). Non-zero = transport or schema breakage.

Usage:
    python3 scripts/probe_aws_knowledge_mcp.py [--verbose]
"""
import json
import sys
import urllib.error
import urllib.request
import uuid

URL = "https://knowledge-mcp.global.api.aws"
TIMEOUT = 60


class MCPClient:
    """Minimal Streamable-HTTP MCP client. No external deps."""

    def __init__(self, url=URL):
        self.url = url
        self.session_id = None
        self._initialize()

    def _post(self, body):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        try:
            r = urllib.request.urlopen(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            return {"_http_error": e.code, "body": e.read().decode()[:500]}
        sid = r.headers.get("Mcp-Session-Id")
        if sid and not self.session_id:
            self.session_id = sid
        ct = r.headers.get("Content-Type", "")
        raw = r.read().decode()
        if not raw:
            return None
        if "text/event-stream" in ct:
            payloads = [
                json.loads(line[6:])
                for line in raw.splitlines()
                if line.startswith("data: ") and line[6:].strip()
            ]
            return payloads[0] if len(payloads) == 1 else payloads
        return json.loads(raw)

    def _initialize(self):
        self._post(
            {
                "jsonrpc": "2.0",
                "id": "init",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "probe", "version": "1.0"},
                },
            }
        )

    def list_tools(self):
        return self._post({"jsonrpc": "2.0", "id": "lt", "method": "tools/list"})

    def call(self, name, args=None):
        return self._post(
            {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {"name": name, "arguments": args or {}},
            }
        )


def _ok(label, resp, verbose=False):
    if not resp:
        print(f"[ FAIL ] {label}: empty response")
        return False
    if isinstance(resp, dict) and resp.get("_http_error"):
        print(f"[ FAIL ] {label}: HTTP {resp['_http_error']} {resp.get('body', '')[:120]}")
        return False
    res = resp.get("result", resp) if isinstance(resp, dict) else resp
    # Accept tool-level errors as still-reachable (schema matters)
    if isinstance(res, dict) and res.get("isError") is True:
        print(f"[ WARN ] {label}: tool returned error (expected for some probes)")
        if verbose:
            print(f"           {json.dumps(res)[:300]}")
        return True
    print(f"[  OK  ] {label}")
    if verbose and isinstance(res, dict) and "content" in res:
        first = res["content"][0].get("text", "") if res["content"] else ""
        print(f"           {first[:200]}")
    return True


def main(argv):
    verbose = "--verbose" in argv or "-v" in argv
    client = MCPClient()
    if not client.session_id:
        print("[ FAIL ] could not establish MCP session")
        return 1

    results = []

    # 1. tools/list
    tl = client.list_tools()
    if tl is None:
        print("[ FAIL ] tools/list returned no payload")
        return 1
    if isinstance(tl, dict):
        tools = tl.get("result", {}).get("tools", [])
    else:
        tools = tl[0].get("result", {}).get("tools", []) if tl else []
    expected = {
        "aws___read_documentation",
        "aws___search_documentation",
        "aws___recommend",
        "aws___list_regions",
        "aws___get_regional_availability",
        "aws___retrieve_skill",
    }
    actual = {t["name"] for t in tools}
    missing = expected - actual
    if missing:
        print(f"[ FAIL ] tools/list missing: {sorted(missing)}")
        results.append(False)
    else:
        print(f"[  OK  ] tools/list — all 6 tools present")
        results.append(True)

    # 2-7. live calls covering the 7 retrieval recipes
    results.append(
        _ok(
            "search_documentation: plugin matrix",
            client.call(
                "aws___search_documentation",
                {"search_phrase": "Amazon OpenSearch Service supported plugins", "limit": 3},
            ),
            verbose,
        )
    )
    results.append(
        _ok(
            "read_documentation: OR1 page",
            client.call(
                "aws___read_documentation",
                {
                    "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/or1.html",
                    "max_length": 1500,
                },
            ),
            verbose,
        )
    )
    results.append(
        _ok(
            "list_regions",
            client.call("aws___list_regions"),
            verbose,
        )
    )
    results.append(
        _ok(
            "get_regional_availability: OpenSearch Serverless in GovCloud",
            client.call(
                "aws___get_regional_availability",
                {
                    "resource_type": "product",
                    "regions": ["us-gov-west-1", "us-gov-east-1"],
                    "filters": ["Amazon OpenSearch Serverless"],
                },
            ),
            verbose,
        )
    )
    results.append(
        _ok(
            "recommend (probe — uses docs URL)",
            client.call(
                "aws___recommend",
                {
                    "url": "https://docs.aws.amazon.com/opensearch-service/latest/developerguide/what-is.html"
                },
            ),
            verbose,
        )
    )
    results.append(
        _ok(
            "retrieve_skill (probe — error-on-not-found is expected)",
            client.call("aws___retrieve_skill", {"skill_name": "nonexistent"}),
            verbose,
        )
    )

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} probes passed")
    return 0 if passed == total else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

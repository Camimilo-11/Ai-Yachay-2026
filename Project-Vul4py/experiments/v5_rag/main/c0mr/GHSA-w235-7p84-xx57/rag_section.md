Reference fixes from OTHER projects, retrieved automatically because their code resembles the hinted code. They may not apply to this project and they are not evidence about these files: take them only as ideas, and back every statement with the files below.

[R1] src/requests/adapters.py (weakness: CWE-670)
```diff
@@ -61,12 +62,38 @@ except ImportError:
         raise InvalidSchema("Missing dependencies for SOCKS support.")
 
 
+if typing.TYPE_CHECKING:
+    from .models import PreparedRequest
+
+
 DEFAULT_POOLBLOCK = False
 DEFAULT_POOLSIZE = 10
 DEFAULT_RETRIES = 0
 DEFAULT_POOL_TIMEOUT = None
 
 
+def _urllib3_request_context(
+    request: "PreparedRequest", verify: "bool | str | None"
+) -> "(typing.Dict[str, typing.Any], typing.Dict[str, typing.Any])":
+    host_params = {}
+    pool_kwargs = {}
+    parsed_request_url = urlparse(request.url)
+    scheme = parsed_request_url.scheme.lower()
+    port = parsed_request_url.port
+    cert_reqs = "CERT_REQUIRED"
+    if verify is False:
+        cert_reqs = "CERT_NONE"
+    if isinstance(verify, str):
+        pool_kwargs["ca_certs"] = verify
+    pool_kwargs["cert_reqs"] = cert_reqs
+    host_params = {
+        "scheme": scheme,
+        "host": parsed_request_url.hostname,
+        "port": port,
+    }
+    return host_params, pool_kwargs
+
+
 class BaseAdapter:
     """The Base Transport Adapter"""
 
```

[R2] src/urllib3/util/retry.py (weakness: CWE-669)
```diff
@@ -235,7 +235,9 @@ class Retry(object):
     RETRY_AFTER_STATUS_CODES = frozenset([413, 429, 503])
 
     #: Default headers to be used for ``remove_headers_on_redirect``
-    DEFAULT_REMOVE_HEADERS_ON_REDIRECT = frozenset(["Cookie", "Authorization"])
+    DEFAULT_REMOVE_HEADERS_ON_REDIRECT = frozenset(
+        ["Cookie", "Authorization", "Proxy-Authorization"]
+    )
 
     #: Maximum backoff time.
     DEFAULT_BACKOFF_MAX = 120
```

[R3] src/urllib3/poolmanager.py (weakness: CWE-601)
```diff
@@ -203,6 +203,22 @@ class PoolManager(RequestMethods):
         **connection_pool_kw: typing.Any,
     ) -> None:
         super().__init__(headers)
+        if "retries" in connection_pool_kw:
+            retries = connection_pool_kw["retries"]
+            if not isinstance(retries, Retry):
+                # When Retry is initialized, raise_on_redirect is based
+                # on a redirect boolean value.
+                # But requests made via a pool manager always set
+                # redirect to False, and raise_on_redirect always ends
+                # up being False consequently.
+                # Here we fix the issue by setting raise_on_redirect to
+                # a value needed by the pool manager without considering
+                # the redirect boolean.
+                raise_on_redirect = retries is not False
+                retries = Retry.from_int(retries, redirect=False)
+                retries.raise_on_redirect = raise_on_redirect
+                connection_pool_kw = connection_pool_kw.copy()
+                connection_pool_kw["retries"] = retries
         self.connection_pool_kw = connection_pool_kw
 
         self.pools: RecentlyUsedContainer[PoolKey, HTTPConnectionPool]
```

Mitigations that MITRE's CWE list gives for these weaknesses:
- CWE-670 Always-Incorrect Control Flow Implementation: The code contains a control flow path that does not reflect the algorithm that the path is intended to implement, leading to incorrect behavior any time this path is navigated.
- CWE-669 Incorrect Resource Transfer Between Spheres: The product does not properly transfer a resource/behavior to another sphere, or improperly imports a resource/behavior from another sphere, in a manner that provides unintended control over that resource.


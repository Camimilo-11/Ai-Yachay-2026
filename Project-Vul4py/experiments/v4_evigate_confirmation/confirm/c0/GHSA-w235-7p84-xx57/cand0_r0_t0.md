## Vulnerability

**CWE-113: HTTP header injection.** In `tornado/curl_httpclient.py`, the curl client formats request header names and values and passes them to `pycurl.HTTPHEADER` without checking for carriage returns or line feeds. In `tornado/http1connection.py`, the HTTP/1 writer rejects line feeds but allows bare carriage returns before writing the serialized message.

If an application places attacker-controlled text in an outgoing header, a line break in that text can be interpreted by a downstream parser as a header boundary. The curl path allows both carriage returns and line feeds through; the HTTP/1 path is vulnerable when the receiving parser treats a bare carriage return as a line ending.

```json
{"evidence":[{"file":"tornado/curl_httpclient.py","line":351,"quote":"            pycurl.HTTPHEADER,"},{"file":"tornado/curl_httpclient.py","line":354,"quote":"                % (native_str(k).encode(\"ASCII\"), native_str(v).encode(\"ISO8859-1\"))"},{"file":"tornado/curl_httpclient.py","line":355,"quote":"                for k, v in request.headers.get_all()"},{"file":"tornado/http1connection.py","line":452,"quote":"            native_str(n) + \": \" + native_str(v) for n, v in headers.get_all()"},{"file":"tornado/http1connection.py","line":456,"quote":"            if b\"\\n\" in line:"},{"file":"tornado/http1connection.py","line":465,"quote":"            data = b\"\\r\\n\".join(lines) + b\"\\r\\n\\r\\n\""},{"file":"tornado/http1connection.py","line":468,"quote":"            self._pending_write = self.stream.write(data)"}]}
```

## Fix

Reject both `\r` and `\n` in each formatted curl header before passing the list to PycURL, and extend the HTTP/1 writer’s existing line check to reject `\r` as well. Both checks run before protocol line endings are added, so valid headers keep their existing encoding, order, and wire format.

## Patch

```diff
--- a/tornado/curl_httpclient.py
+++ b/tornado/curl_httpclient.py
@@ -347,14 +347,16 @@
         if "Pragma" not in request.headers:
             request.headers["Pragma"] = ""
 
-        curl.setopt(
-            pycurl.HTTPHEADER,
-            [
-                b"%s: %s"
-                % (native_str(k).encode("ASCII"), native_str(v).encode("ISO8859-1"))
-                for k, v in request.headers.get_all()
-            ],
-        )
+        header_list = []
+        for k, v in request.headers.get_all():
+            header = b"%s: %s" % (
+                native_str(k).encode("ASCII"),
+                native_str(v).encode("ISO8859-1"),
+            )
+            if b"\r" in header or b"\n" in header:
+                raise ValueError("Newline in header: " + repr(header))
+            header_list.append(header)
+        curl.setopt(pycurl.HTTPHEADER, header_list)
 
         curl.setopt(
             pycurl.HEADERFUNCTION,
--- a/tornado/http1connection.py
+++ b/tornado/http1connection.py
@@ -453,7 +453,7 @@
         )
         lines.extend(line.encode("latin1") for line in header_lines)
         for line in lines:
-            if b"\n" in line:
+            if b"\r" in line or b"\n" in line:
                 raise ValueError("Newline in header: " + repr(line))
         future = None
         if self.stream.closed():
```

## Self-assessment

```json
{"claim":1,"confidence":0.99}
```

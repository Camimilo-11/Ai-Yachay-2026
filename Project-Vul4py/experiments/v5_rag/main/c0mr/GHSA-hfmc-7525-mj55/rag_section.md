Reference fixes from OTHER projects, retrieved automatically because their code resembles the hinted code. They may not apply to this project and they are not evidence about these files: take them only as ideas, and back every statement with the files below.

[R1] zhmcclient/_session.py (weakness: CWE-312)
```diff
@@ -39,7 +39,7 @@ from ._constants import DEFAULT_CONNECT_TIMEOUT, DEFAULT_CONNECT_RETRIES, \
     DEFAULT_OPERATION_TIMEOUT, DEFAULT_STATUS_TIMEOUT, \
     DEFAULT_NAME_URI_CACHE_TIMETOLIVE, HMC_LOGGER_NAME, \
     HTML_REASON_WEB_SERVICES_DISABLED, HTML_REASON_OTHER, \
-    DEFAULT_HMC_PORT
+    DEFAULT_HMC_PORT, BLANKED_OUT_STRING
 from ._utils import repr_obj_id
 from ._version import __version__
 
```

[R2] jwt/algorithms.py (weakness: CWE-327)
```diff
@@ -551,26 +546,28 @@ if has_crypto:
             pass
 
         def prepare_key(self, key):
-
-            if isinstance(
-                key,
-                (Ed25519PrivateKey, Ed25519PublicKey, Ed448PrivateKey, Ed448PublicKey),
-            ):
-                return key
-
             if isinstance(key, (bytes, str)):
                 if isinstance(key, str):
                     key = key.encode("utf-8")
                 str_key = key.decode("utf-8")
 
                 if "-----BEGIN PUBLIC" in str_key:
-                    return load_pem_public_key(key)
-                if "-----BEGIN PRIVATE" in str_key:
-                    return load_pem_private_key(key, password=None)
-                if str_key[0:4] == "ssh-":
-                    return load_ssh_public_key(key)
+                    key = load_pem_public_key(key)
+                elif "-----BEGIN PRIVATE" in str_key:
+                    key = load_pem_private_key(key, password=None)
+                elif str_key[0:4] == "ssh-":
+                    key = load_ssh_public_key(key)
 
-            raise TypeError("Expecting a PEM-formatted or OpenSSH key.")
+            # Explicit check the key to prevent confusing errors from cryptography
+            if not isinstance(
+                key,
+                (Ed25519PrivateKey, Ed25519PublicKey, Ed448PrivateKey, Ed448PublicKey),
+            ):
+                raise InvalidKeyError(
+                    "Expecting a EllipticCurvePrivateKey/EllipticCurvePublicKey. Wrong key provided for EdDSA algorithms"
+                )
+
+            return key
 
         def sign(self, msg, key):
             """
```

[R3] src/mcp/shared/session.py (weakness: CWE-248)
```diff
@@ -333,90 +333,107 @@ class BaseSession(
             self._read_stream,
             self._write_stream,
         ):
-            async for message in self._read_stream:
-                if isinstance(message, Exception):
-                    await self._handle_incoming(message)
-                elif isinstance(message.message.root, JSONRPCRequest):
-                    try:
-                        validated_request = self._receive_request_type.model_validate(
-                            message.message.root.model_dump(by_alias=True, mode="json", exclude_none=True)
-                        )
-                        responder = RequestResponder(
-                            request_id=message.message.root.id,
-                            request_meta=validated_request.root.params.meta if validated_request.root.params else None,
-                            request=validated_request,
-                            session=self,
-                            on_complete=lambda r: self._in_flight.pop(r.request_id, None),
-                            message_metadata=message.metadata,
-                        )
-                        self._in_flight[responder.request_id] = responder
-                        await self._received_request(responder)
-
-                        if not responder._completed:  # type: ignore[reportPrivateUsage]
-                            await self._handle_incoming(responder)
-                    except Exception as e:
-                        # For request validation errors, send a proper JSON-RPC error
-                        # response instead of crashing the server
-                        logging.warning(f"Failed to validate request: {e}")
-                        logging.debug(f"Message that failed validation: {message.message.root}")
-                        error_response = JSONRPCError(
-                            jsonrpc="2.0",
-                            id=message.message.root.id,
-                            error=ErrorData(
-                                code=INVALID_PARAMS,
-                                message="Invalid request parameters",
-                                data="",
-                            ),
-                        )
-                        session_message = SessionMessage(message=JSONRPCMessage(error_response))
-                        await self._write_stream.send(session_message)
-
-                elif isinstance(message.message.root, JSONRPCNotification):
-                    try:
-                        notification = self._receive_notification_type.model_validate(
-                            message.message.root.model_dump(by_alias=True, mode="json", exclude_none=True)
-                        )
-                        # Handle cancellation notifications
-                        if isinstance(notification.root, CancelledNotification):
-                            cancelled_id = notification.root.params.requestId
-                            if cancelled_id in self._in_flight:
-                                await self._in_flight[cancelled_id].cancel()
... (truncated)
```

Mitigations that MITRE's CWE list gives for these weaknesses:
- CWE-312 Cleartext Storage of Sensitive Information: When storing data in the cloud (e.g., S3 buckets, Azure blobs, Google Cloud Storage, etc.), use the provider's controls to encrypt the data at rest. [REF-1297] [REF-1299] [REF-1301]; In some systems/environments such as cloud, the use of "double encryption" (at both the software and hardware layer) might be required, and the developer might be solely responsible for both layers, instead of shared responsibility with the administrator of the broader system/environment.
- CWE-327 Use of a Broken or Risky Cryptographic Algorithm: When using industry-approved techniques, use them correctly. Don't cut corners by skipping resource-intensive steps (CWE-325). These steps are often essential for preventing common attacks.; When there is a need to store or transmit sensitive data, use strong, up-to-date cryptographic algorithms to encrypt that data. Select a well-vetted algorithm that is currently considered to be strong by experts in the field, and use well-tested implementations. As with all cryptographic mechanisms, the source code should be available for analysis. For example, US government systems require FIPS 140-2 certification [REF-1192]. Do not develop custom or private cryptographic algorithms. They will likely be exposed to attacks that are well-understood by cryptographers. Reverse engineering techniques are mature. If the algorithm can be compromised if attackers find out how it works, then it is especially weak. Periodically ensure that the cryptography has not become obsolete. Some older algorithms, once thought to require a billion years of computing time, can now be broken in days or hours. This includes MD4, MD5, SHA1, DES, and other algorithms that were once regarded as strong. [REF-267]; Ensure that the design allows one cryptographic algorithm to be replaced with another in the next generation or version. Where possible, use wrappers to make the interfaces uniform. This will make it easier to upgrade to stronger algorithms. With hardware, design the product at the Intellectual Property (IP) level so that one ... (truncated)


## Vulnerability

**SSH transport integrity failure (Terrapin, CVE-2023-48795; CWE-345).** In `asyncssh/connection.py`, `_recv_packet()` advances the receive sequence number for plaintext packets, then uses that same counter to verify encrypted packets after `NEWKEYS`. The initial key exchange neither requires `KEXINIT` to be the first packet nor resets the counters at the encryption boundary. With susceptible cipher and MAC combinations, an on-path attacker can exploit this to suppress early encrypted messages, such as extension negotiation, without triggering an integrity error.

```json
{"evidence":[{"file":"asyncssh/connection.py","line":1316,"quote":"        self._inpbuf += data"},{"file":"asyncssh/connection.py","line":1506,"quote":"        seq = self._recv_seq"},{"file":"asyncssh/connection.py","line":1511,"quote":"            packet_data = self._recv_encryption.decrypt_packet("},{"file":"asyncssh/connection.py","line":1512,"quote":"                seq, self._packet, rest, 4, mac)"},{"file":"asyncssh/connection.py","line":1517,"quote":"            packet_data = self._packet[4:] + rest"},{"file":"asyncssh/connection.py","line":1579,"quote":"                processed = handler.process_packet(pkttype, seq, packet)"},{"file":"asyncssh/connection.py","line":1594,"quote":"            self._recv_seq = (seq + 1) & 0xffffffff"},{"file":"asyncssh/connection.py","line":1648,"quote":"        self._send_seq = (seq + 1) & 0xffffffff"},{"file":"asyncssh/connection.py","line":1404,"quote":"        return [b'ext-info-c' if self.is_client() else b'ext-info-s']"},{"file":"asyncssh/connection.py","line":2269,"quote":"            self._recv_encryption = self._next_recv_encryption"}]}
```

## Fix

Negotiate strict key exchange using the role-specific OpenSSH markers. When negotiated, require `KEXINIT` to be the first packet, reject unexpected packets during the initial exchange, and reset each direction’s sequence counter after its `NEWKEYS` packet, including during rekeying. Reject receive-counter wrap before keys are installed so it cannot defeat the first-packet check.

Peers that do not advertise strict key exchange retain legacy sequence numbering and normal interoperability, but do not gain the negotiated Terrapin protection. Tests were not run.

## Patch

```diff
--- a/asyncssh/connection.py
+++ b/asyncssh/connection.py
@@ -860,7 +860,8 @@
         self._kex: Optional[Kex] = None
         self._kexinit_sent = False
         self._kex_complete = False
         self._ignore_first_kex = False
+        self._strict_kex = False
 
         self._gss: Optional[GSSBase] = None
         self._gss_kex = False
@@ -1398,10 +1399,15 @@
             (alg_type, b','.join(local_algs).decode('ascii'),
              b','.join(remote_algs).decode('ascii')))
 
-    def _get_ext_info_kex_alg(self) -> List[bytes]:
-        """Return the kex alg to add if any to request extension info"""
+    def _get_extra_kex_algs(self) -> List[bytes]:
+        """Return extension markers for the initial key exchange"""
 
-        return [b'ext-info-c' if self.is_client() else b'ext-info-s']
+        if self._session_id:
+            return []
+        elif self.is_client():
+            return [b'ext-info-c', b'kex-strict-c-v00@openssh.com']
+        else:
+            return [b'ext-info-s', b'kex-strict-s-v00@openssh.com']
 
     def _send(self, data: bytes) -> None:
         """Send data to the SSH connection"""
@@ -1546,6 +1552,10 @@
             else:
                 skip_reason = 'kex not in progress'
                 exc_reason = 'Key exchange not in progress'
+        elif (self._strict_kex and not self._recv_encryption and
+              pkttype not in (MSG_DISCONNECT, MSG_KEXINIT, MSG_NEWKEYS)):
+            skip_reason = 'invalid packet during initial kex'
+            exc_reason = 'Unexpected packet during initial key exchange'
         elif MSG_USERAUTH_FIRST <= pkttype <= MSG_USERAUTH_LAST:
             if self._auth:
                 handler = self._auth
@@ -1581,6 +1591,10 @@
                 raise ProtocolError(str(exc)) from None
 
             if not processed:
+                if self._strict_kex and not self._recv_encryption:
+                    raise ProtocolError('Unexpected packet during '
+                                        'initial key exchange')
+
                 self.logger.debug1('Unknown packet type %d received', pkttype)
                 self.send_packet(MSG_UNIMPLEMENTED, UInt32(seq))
 
@@ -1591,7 +1605,13 @@
             self._auth_final = True
 
         if self._transport:
-            self._recv_seq = (seq + 1) & 0xffffffff
+            if pkttype == MSG_NEWKEYS and self._strict_kex:
+                self._recv_seq = 0
+            elif seq == 0xffffffff and not self._recv_encryption:
+                raise ProtocolError('Sequence number wrapped before keys')
+            else:
+                self._recv_seq = (seq + 1) & 0xffffffff
+
             self._recv_handler = self._recv_pkthdr
 
         return True
@@ -1645,7 +1665,11 @@
             mac = b''
 
         self._send(packet + mac)
-        self._send_seq = (seq + 1) & 0xffffffff
+
+        if pkttype == MSG_NEWKEYS and self._strict_kex:
+            self._send_seq = 0
+        else:
+            self._send_seq = (seq + 1) & 0xffffffff
 
         if self._kex_complete:
             self._rekey_bytes_sent += pktlen
@@ -1689,7 +1713,7 @@
 
         kex_algs = expand_kex_algs(self._kex_algs, gss_mechs,
                                    bool(self._server_host_key_algs)) + \
-                   self._get_ext_info_kex_alg()
+                   self._get_extra_kex_algs()
 
         host_key_algs = self._server_host_key_algs or [b'null']
 
@@ -2191,14 +2215,19 @@
         if self.is_server():
             self._client_kexinit = packet.get_consumed_payload()
-
-            if b'ext-info-c' in peer_kex_algs and not self._session_id:
-                self._can_send_ext_info = True
+            ext_info = b'ext-info-c'
+            strict_kex = b'kex-strict-c-v00@openssh.com'
         else:
             self._server_kexinit = packet.get_consumed_payload()
+            ext_info = b'ext-info-s'
+            strict_kex = b'kex-strict-s-v00@openssh.com'
 
-            if b'ext-info-s' in peer_kex_algs and not self._session_id:
-                self._can_send_ext_info = True
+        if not self._session_id:
+            self._can_send_ext_info = ext_info in peer_kex_algs
+            self._strict_kex = strict_kex in peer_kex_algs
+
+        if self._strict_kex and not self._recv_encryption and self._recv_seq:
+            raise ProtocolError('KEXINIT was not the first packet')
 
         if self._kexinit_sent:
             self._kexinit_sent = False
         else:
```

## Self-assessment

```json
{"claim":1,"confidence":0.94}
```

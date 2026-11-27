## Review

**P1 – Terrapin (prefix truncation) fix via strict KEX**

*Does it remove the vulnerability?*

1. **Strict KEX is advertised.** During the initial exchange, `_get_kex_ext_algs` adds the role-specific `kex-strict-{c,s}-v00@openssh.com` marker. It is added to the KEXINIT list in `_send_kexinit` at the call site `kex_algs = expand_kex_algs(...) + ...`.

2. **Strict KEX is negotiated from the peer's marker.** In `_process_kexinit`, strict mode is set only if the peer advertised the opposite-role marker, and only on the first exchange (`if not self._session_id`). An attacker cannot strip the marker. The original code records the KEXINIT into the exchange hash at `self._client_kexinit = packet.get_consumed_payload()`.

3. **KEXINIT must be the first packet.** The patch raises `ProtocolError` if `self._recv_seq != 0` when the peer's KEXINIT is processed. This defeats the classic Terrapin injection. If an attacker inserts `MSG_IGNORE` before the peer's KEXINIT:
   - the original increment `self._recv_seq = (seq + 1) & 0xffffffff` makes KEXINIT arrive with seq 1;
   - the connection is then rejected.
   - The rollover guard prevents an attacker from wrapping the counter back to 0 before KEXINIT.

4. **Sequence numbers reset at NEWKEYS, in both directions.**
   - Receive: after processing `MSG_NEWKEYS` in strict mode, `_recv_seq = 0`. That is exactly when `_process_newkeys` installs the new keys (`self._recv_encryption = self._next_recv_encryption`).
   - Send: `send_packet` zeroes `_send_seq` after transmitting NEWKEYS. `send_newkeys` installs the new send keys after `self.send_packet(MSG_NEWKEYS)`, so the first encrypted packet uses seq 0.
   - This applies at rekey too, matching OpenSSH semantics.
   - Any packet dropped after NEWKEYS therefore causes a MAC or sequence mismatch.

5. **Unexpected packets during the initial exchange are rejected.** In strict mode, before receive encryption is installed:
   - non-KEX packets other than DISCONNECT are rejected;
   - unprocessed KEX-range packets raise instead of sending `MSG_UNIMPLEMENTED`.

*Does it preserve functionality?*

- Non-strict peers keep the existing behaviour: same sequence handling and the same `MSG_UNIMPLEMENTED` path.
- asyncssh itself sends no non-KEX packets before NEWKEYS. `MSG_IGNORE` is only inserted when `self._send_encryption` is set. `MSG_EXT_INFO` is sent after the new keys are installed.
- So strict peers interoperate, and rekey works because the strict flag persists.
- The renamed private helper is not public API.
- The 2^32 pre-encryption rollover guard cannot be reached in practice.

Overall this matches the upstream approach. Residual risk: tests might reference the old private helper name, and I could not run anything.

## Verdict
```json
{"candidates": {"P1": {"removes_vulnerability": 1, "preserves_functionality": 1, "claim": 1, "confidence": 0.8, "evidence": [{"file": "asyncssh/connection.py", "line": 1592, "quote": "            self._recv_seq = (seq + 1) & 0xffffffff"}, {"file": "asyncssh/connection.py", "line": 1646, "quote": "        self._send_seq = (seq + 1) & 0xffffffff"}, {"file": "asyncssh/connection.py", "line": 1791, "quote": "        self.send_packet(MSG_NEWKEYS)"}, {"file": "asyncssh/connection.py", "line": 1504, "quote": "        seq = self._recv_seq"}], "counterexample": ""}}, "best": "P1"}
```

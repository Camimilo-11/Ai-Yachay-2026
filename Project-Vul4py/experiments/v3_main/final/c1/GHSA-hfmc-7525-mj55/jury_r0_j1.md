## Review

**P1** implements the strict key exchange mitigation for Terrapin (the "kex-strict-*-v00@openssh.com" extension), and I found no bypass or regression.

- **Negotiation.** `_get_kex_ext_algs` advertises the role-specific strict marker only when no session ID exists, so only on the first key exchange. `_process_kexinit` sets `_strict_kex` when the peer's marker is present and `_session_id` is empty. Both sides therefore agree, and the flag persists through rekeys.
- **First-packet check.** `_process_kexinit` runs while `self._recv_seq` still holds the current packet's sequence number, because the increment happens at the end of `_recv_packet`. The `_recv_seq != 0` test therefore correctly requires KEXINIT to be the first packet. An attacker who injects an `IGNORE`, or who drops a packet, shifts the counter and the check fires.
- **Pre-key packet filter.** The new `elif` only sees non-KEX types (below 20) before `_recv_encryption` is set. It rejects `IGNORE`, `DEBUG`, `EXT_INFO` and similar, and allows `DISCONNECT`. `NEWKEYS` (21) falls in the KEX range and is handled by the first branch. This is consistent with the strict-mode rules.
- **Sequence reset.** The receive side resets to 0 on `NEWKEYS`, including on rekey. The send side resets to 0 after `NEWKEYS` is written. This is the core Terrapin fix. The send side is correct: the `NEWKEYS` packet itself is encrypted and MACed with its own sequence number before the reset.
- **Rollover guard.** The pre-key rollover guard closes the case where 2^32 pre-key packets would wrap the counter back to 0 and defeat the first-packet check.
- **Compatibility.** Peers that do not advertise the marker keep the legacy behaviour, since `_strict_kex` stays false. For peers that do negotiate strict mode, the packet filter and sequence reset follow the strict-mode rules.

Residual risk: tests were not run, and `send_packet`'s recursive `IGNORE` insertion before `NEWKEYS` interacts with the send-side reset. That ordering looks correct, because the `IGNORE` is sent first and the reset happens after the `NEWKEYS` write.

## Verdict
```json
{"candidates": {"P1": {"removes_vulnerability": 1, "preserves_functionality": 1, "claim": 1, "confidence": 0.82, "evidence": [{"file": "asyncssh/connection.py", "line": 1592, "quote": "            self._recv_seq = (seq + 1) & 0xffffffff"}, {"file": "asyncssh/connection.py", "line": 1646, "quote": "        self._send_seq = (seq + 1) & 0xffffffff"}, {"file": "asyncssh/connection.py", "line": 1404, "quote": "        return [b'ext-info-c' if self.is_client() else b'ext-info-s']"}], "counterexample": ""}}, "best": "P1"}
```

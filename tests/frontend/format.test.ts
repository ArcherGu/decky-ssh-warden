// Formatting helpers. Run with `node --test` (Node strips the types).
import assert from "node:assert/strict";
import { test } from "node:test";
import { minutesUntil, sshCommand } from "../../src/format.ts";

test("ssh commands leave out the default port", () => {
  assert.equal(sshCommand("ssh", "deck", "192.168.1.5", 22), "ssh deck@192.168.1.5");
  assert.equal(sshCommand("ssh", "deck", "192.168.1.5", 2222), "ssh -p 2222 deck@192.168.1.5");
  assert.equal(sshCommand("ssh-copy-id", "deck", "10.0.0.2", 2222), "ssh-copy-id -p 2222 deck@10.0.0.2");
});

test("minutes until a deadline round up and never go negative", () => {
  const now = Date.now() / 1000;
  assert.equal(minutesUntil(now + 90), 2);
  assert.equal(minutesUntil(now + 30 * 60 - 1), 30);
  assert.equal(minutesUntil(now - 60), 0);
});

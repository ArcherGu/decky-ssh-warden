// Language choice and backend error messages. Run with `node --test` (Node strips the types).
import assert from "node:assert/strict";
import { test } from "node:test";

type Steam = { LocalizationManager?: { m_rgLocalesToUse: string[] } };

/** A fresh copy of i18n.ts, loaded as Steam would with the given UI language. */
async function loadWithLocale(locale: string | undefined) {
  const steam = globalThis as Steam;
  if (locale === undefined) delete steam.LocalizationManager;
  else steam.LocalizationManager = { m_rgLocalesToUse: [locale] };
  try {
    return await import(`../../src/i18n.ts?locale=${locale}`);
  } finally {
    delete steam.LocalizationManager;
  }
}

test("Simplified Chinese Steam gets Chinese, every other language English", async () => {
  assert.equal((await loadWithLocale("zh-cn")).t.service.enable, "启用 SSH");
  assert.equal((await loadWithLocale("zh-hans")).t.service.enable, "启用 SSH");
  for (const locale of ["en-us", "zh-tw", "ja", "de-de"]) {
    assert.equal((await loadWithLocale(locale)).t.service.enable, "Enable SSH", locale);
  }
});

test("without Steam's localization the browser language decides", async () => {
  const { t } = await loadWithLocale(undefined);
  const expected = navigator.language.toLowerCase().startsWith("zh-cn") ? "启用 SSH" : "Enable SSH";
  assert.equal(t.service.enable, expected);
});

test("backend errors are shown in the panel's language, unknown codes fall back", async () => {
  const zh = await loadWithLocale("zh-cn");
  assert.equal(zh.errorMessage("port_in_use", { port: 1337, owner: "Decky Loader" }, "fallback"), "端口 1337 已被 Decky Loader 占用");
  assert.equal(zh.errorMessage("no_such_code", {}, "English from the backend"), "English from the backend");
  assert.equal(zh.errorMessage(undefined, undefined, "plain error"), "plain error");
  const en = await loadWithLocale("en-us");
  assert.equal(en.errorMessage("account_locked", {}, "fallback"), "The deck account is locked; its password cannot be changed here");
});

test("both languages have the same strings", async () => {
  const shape = (value: unknown): unknown =>
    typeof value === "object" && value !== null
      ? Object.fromEntries(Object.entries(value).map(([k, v]) => [k, shape(v)]))
      : typeof value;
  const zh = (await loadWithLocale("zh-cn")).t;
  const en = (await loadWithLocale("en-us")).t;
  assert.deepEqual(shape(zh), shape(en));
});
